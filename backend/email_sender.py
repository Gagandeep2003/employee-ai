"""Outbound email via plain SMTP (stdlib smtplib) -- works with any provider
(Resend, Brevo, SES, Gmail app passwords, ...) with no extra dependency and no
vendor lock-in. Sends run in a worker thread so they never block the event loop.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

import config

logger = logging.getLogger("ai-employee.email")


def _send_sync(to_email: str, subject: str, body_text: str, reply_to: str = None) -> bool:
    if not config.EMAIL_ENABLED:
        logger.info("Email not configured; skipping send to %s (%s)", to_email, subject)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.warning("Failed to send email to %s: %s", to_email, e)
        return False


async def send_email(to_email: str, subject: str, body_text: str, reply_to: str = None) -> bool:
    if not to_email:
        return False
    return await asyncio.to_thread(_send_sync, to_email, subject, body_text, reply_to)


async def send_handoff_email(owner_email: str, business_name: str, visitor_name: str,
                             visitor_email: str, note: str, conversation_id: str) -> bool:
    subject = f"[{business_name}] A visitor wants to talk to a human"
    lines = [
        f"Someone chatting with your AI Employee on {business_name} asked to speak with a person.",
        "",
        f"Name: {visitor_name or '(not given)'}",
        f"Email: {visitor_email or '(not given)'}",
        f"Message: {note or '(no message left)'}",
        "",
        f"Conversation ID: {conversation_id}",
        "Reply directly to this email to reach them (if they left an email address).",
    ]
    return await send_email(owner_email, subject, "\n".join(lines), reply_to=visitor_email)


async def send_new_device_login_email(to_email: str, name: str, device_name: str,
                                      ip: str, when_iso: str) -> bool:
    subject = "New sign-in to your account"
    lines = [
        f"Hi {name or ''},",
        "",
        f"Your account was just signed into from a device we haven't seen before:",
        "",
        f"Device: {device_name}",
        f"IP address: {ip or 'unknown'}",
        f"Time: {when_iso}",
        "",
        "If this was you, no action is needed. If you don't recognize this sign-in, change "
        "your password immediately and review your active sessions in Settings -> Security.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_account_locked_email(to_email: str, name: str, lockout_minutes: int) -> bool:
    subject = "Your account was temporarily locked"
    lines = [
        f"Hi {name or ''},",
        "",
        f"We locked your account for {lockout_minutes} minutes after several failed sign-in "
        "attempts, to protect it from password guessing.",
        "",
        "If this was you, just wait and try again shortly, or use 'forgot password' to reset "
        "it now. If it wasn't you, someone may be trying to access your account -- consider "
        "resetting your password once the lock clears.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_api_key_created_email(to_email: str, name: str, key_name: str, business_name: str) -> bool:
    subject = f"New API key created for {business_name}"
    lines = [
        f"Hi {name or ''},",
        "",
        f"A new API key named \"{key_name}\" was just created for {business_name}. If you "
        "didn't create this, revoke it immediately from Settings -> Security -> API keys.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_welcome_email(to_email: str, name: str) -> bool:
    subject = "Welcome to AI Employee"
    lines = [
        f"Hi {name or ''},",
        "",
        "Welcome aboard! Your AI Employee account is ready. Next step: add a business and "
        "either point it at your website or type in a few facts, and your AI receptionist "
        "will be answering customer questions within minutes.",
        "",
        "If you get stuck, just reply to this email.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_upgrade_confirmed_email(to_email: str, name: str, business_name: str, plan_name: str) -> bool:
    subject = f"You're on {plan_name} now"
    lines = [
        f"Hi {name or ''},",
        "",
        f"{business_name} is now on the {plan_name} plan. Your invoice is available any time "
        "from Billing in your dashboard.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_subscription_change_scheduled_email(to_email: str, name: str, business_name: str,
                                                    new_plan_name: str, effective_date: str) -> bool:
    subject = f"{business_name} is switching to {new_plan_name}"
    lines = [
        f"Hi {name or ''},",
        "",
        f"{business_name} will switch to the {new_plan_name} plan on {effective_date}, at the "
        "end of the current billing period -- you'll keep your current plan's access until then. "
        "Changed your mind? You can switch back any time before then from Billing.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_cancellation_confirmed_email(to_email: str, name: str, business_name: str, immediate: bool, access_until: str = None) -> bool:
    subject = f"{business_name}'s subscription is canceled"
    if immediate:
        lines = [f"Hi {name or ''}", "", f"{business_name} has been moved to the free plan, effective now. "
                 "You can resubscribe any time from Billing."]
    else:
        lines = [f"Hi {name or ''}", "", f"{business_name}'s subscription is set to cancel. You'll keep your "
                 f"current plan's access until {access_until}, then move to the free plan. Changed your mind? "
                 "You can undo this any time before then from Billing."]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_referral_reward_email(to_email: str, name: str, referred_business_name: str) -> bool:
    subject = "Your referral just converted!"
    lines = [
        f"Hi {name or ''},",
        "",
        f"Good news -- someone you referred ({referred_business_name}) just subscribed to a paid "
        "plan. Check Referrals in your dashboard for your reward details.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_quota_alert_email(to_email: str, name: str, business_name: str, threshold: int, used: int, limit: int) -> bool:
    if threshold >= 100:
        subject = f"{business_name} has hit its monthly chat limit"
        headline = (f"{business_name} has used all {limit} chats included in its plan this month. "
                    "New conversations may be paused until next month, or until you upgrade.")
    else:
        subject = f"{business_name} is at {threshold}% of its monthly chat limit"
        headline = f"{business_name} has used {used} of {limit} chats included in its plan this month ({threshold}%+)."
    lines = [
        f"Hi {name or ''}",
        "",
        headline,
        "",
        "If you'd like more headroom, you can upgrade your plan any time from Billing in your dashboard.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_renewal_reminder_email(to_email: str, name: str, business_name: str, renews_by: str) -> bool:
    subject = f"Your {business_name} plan renews soon"
    lines = [
        f"Hi {name or ''},",
        "",
        f"Your paid plan for {business_name} is set to renew around {renews_by}. Head to "
        "Billing in your dashboard to renew and keep uninterrupted service.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_past_due_email(to_email: str, name: str, business_name: str, grace_days: int) -> bool:
    subject = f"Action needed: renew your {business_name} plan"
    lines = [
        f"Hi {name or ''},",
        "",
        f"Your plan for {business_name} wasn't renewed in time. We're giving you a {grace_days}-day "
        "grace period with no interruption to your AI Employee while you sort it out -- "
        "renew from Billing in your dashboard before the grace period ends to avoid being "
        "moved to the free plan.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_downgraded_email(to_email: str, name: str, business_name: str) -> bool:
    subject = f"{business_name} moved to the free plan"
    lines = [
        f"Hi {name or ''},",
        "",
        f"{business_name} wasn't renewed within the grace period, so it's been moved to the "
        "free plan. Your AI Employee is still running, just at the free plan's chat limit. "
        "Renew any time from Billing in your dashboard.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_refund_processed_email(to_email: str, name: str, business_name: str, amount_display: str) -> bool:
    subject = f"Refund processed for {business_name}"
    lines = [
        f"Hi {name or ''},",
        "",
        f"A refund of {amount_display} for {business_name} has been processed and should "
        "appear on your original payment method within a few business days, depending on "
        "your bank.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_booking_email(owner_email: str, business_name: str, service: str,
                             start_time: str, customer_name: str, customer_phone: str,
                             customer_email: str, reference: str) -> bool:
    subject = f"[{business_name}] New appointment booked: {service}"
    lines = [
        f"Your AI Employee just booked an appointment on {business_name}.",
        "",
        f"Service: {service}",
        f"When: {start_time}",
        f"Customer: {customer_name}",
        f"Phone: {customer_phone or '(not given)'}",
        f"Email: {customer_email or '(not given)'}",
        f"Reference: {reference}",
    ]
    return await send_email(owner_email, subject, "\n".join(lines), reply_to=customer_email)
