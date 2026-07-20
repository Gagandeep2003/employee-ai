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
