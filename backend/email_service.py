"""Provider-independent email service supporting Resend, Brevo, and SMTP.

This module abstracts email sending behind a unified interface so providers
can be switched via configuration without changing application logic.
Uses HTTP APIs (Resend/Brevo) as primary providers with SMTP as fallback.
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from email.message import EmailMessage  # Moved to top level for type hints

import config

logger = logging.getLogger("roviq-ai.email")


class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    async def send(self, to_email: str, subject: str, body_text: str, 
                   body_html: Optional[str] = None, reply_to: Optional[str] = None,
                   cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> bool:
        """Send an email. Returns True on success."""
        pass


class ResendProvider(EmailProvider):
    """Email provider using Resend HTTP API."""
    
    def __init__(self, api_key: str, from_email: str, from_name: str):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.base_url = "https://api.resend.com/emails"
    
    async def send(self, to_email: str, subject: str, body_text: str,
                   body_html: Optional[str] = None, reply_to: Optional[str] = None,
                   cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> bool:
        if not self.api_key:
            logger.warning("Resend API key not configured")
            return False
        
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": subject,
                "text": body_text,
            }
            
            if body_html:
                payload["html"] = body_html
            
            if reply_to:
                payload["reply_to"] = reply_to

            if cc:
                payload["cc"] = cc
            
            if bcc:
                payload["bcc"] = bcc
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info("Email sent via Resend to %s", to_email)
                        return True
                    else:
                        error_text = await resp.text()
                        logger.warning("Resend API error %s: %s", resp.status, error_text)
                        return False
        except ImportError:
            logger.error("aiohttp not installed for Resend provider")
            return False
        except Exception as e:
            logger.warning("Failed to send email via Resend: %s", e)
            return False


class BrevoProvider(EmailProvider):
    """Email provider using Brevo (Sendinblue) HTTP API."""
    
    def __init__(self, api_key: str, from_email: str, from_name: str):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.base_url = "https://api.brevo.com/v3/smtp/email"
    
    async def send(self, to_email: str, subject: str, body_text: str,
                   body_html: Optional[str] = None, reply_to: Optional[str] = None,
                   cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> bool:
        if not self.api_key:
            logger.warning("Brevo API key not configured")
            return False
        
        try:
            import aiohttp
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            sender = {"name": self.from_name, "email": self.from_email}
            
            # Brevo prefers HTML, but we can send text-only
            content = []
            if body_html:
                content.append({"type": "html", "value": body_html})
            else:
                content.append({"type": "text", "value": body_text})
            
            payload = {
                "sender": sender,
                "to": [{"email": to_email}],
                "subject": subject,
                "content": content,
            }
            
            if reply_to:
                payload["replyTo"] = {"email": reply_to}

            if cc:
                payload["cc"] = [{"email": e} for e in cc]
            
            if bcc:
                payload["bcc"] = [{"email": e} for e in bcc]
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info("Email sent via Brevo to %s", to_email)
                        return True
                    else:
                        error_text = await resp.text()
                        logger.warning("Brevo API error %s: %s", resp.status, error_text)
                        return False
        except ImportError:
            logger.error("aiohttp not installed for Brevo provider")
            return False
        except Exception as e:
            logger.warning("Failed to send email via Brevo: %s", e)
            return False


class SMTPFallbackProvider(EmailProvider):
    """Fallback email provider using SMTP (stdlib)."""
    
    def __init__(self, host: str, port: int, user: str, password: str,
                 from_email: str, from_name: str, use_tls: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.use_tls = use_tls
    
    async def send(self, to_email: str, subject: str, body_text: str,
                   body_html: Optional[str] = None, reply_to: Optional[str] = None,
                   cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> bool:
        import smtplib
        
        if not self.host:
            logger.warning("SMTP not configured")
            return False
        
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to

        if cc:
            msg["Cc"] = ", ".join(cc)
        
        if bcc:
            # BCC recipients are not added to headers, just to the sendmail call
            pass
        
        if body_html:
            msg.set_content(body_text)
            msg.add_alternative(body_html, subtype='html')
        else:
            msg.set_content(body_text)
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_sync,
                msg,
                bcc
            )
            logger.info("Email sent via SMTP to %s", to_email)
            return True
        except Exception as e:
            logger.warning("Failed to send email via SMTP: %s", e)
            return False
    
    def _send_sync(self, msg: EmailMessage, bcc: Optional[List[str]] = None):
        import smtplib
        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            if self.use_tls:
                server.starttls()
            if self.user and self.password:
                server.login(self.user, self.password)
            
            # Get all recipient addresses (To + Cc + Bcc)
            all_recipients = [msg["To"]]
            if msg["Cc"]:
                all_recipients.extend(msg["Cc"].split(", "))
            if bcc:
                all_recipients.extend(bcc)
            
            server.send_message(msg, to_addrs=all_recipients)


class EmailService:
    """Unified email service with provider abstraction and fallback."""
    
    def __init__(self):
        self.primary_provider: Optional[EmailProvider] = None
        self.fallback_provider: Optional[EmailProvider] = None
        self._init_providers()
    
    def _init_providers(self):
        """Initialize email providers based on configuration."""
        from_email = config.SMTP_FROM_EMAIL or "noreply@roviq.ai"
        from_name = config.SMTP_FROM_NAME or "Roviq AI"
        
        # Try Resend first (primary HTTP API provider)
        resend_key = os.getenv("RESEND_API_KEY")
        if resend_key:
            self.primary_provider = ResendProvider(
                api_key=resend_key,
                from_email=from_email,
                from_name=from_name
            )
            logger.info("Email service initialized with Resend as primary provider")
        else:
            # Try Brevo as alternative HTTP API provider
            brevo_key = os.getenv("BREVO_API_KEY")
            if brevo_key:
                self.primary_provider = BrevoProvider(
                    api_key=brevo_key,
                    from_email=from_email,
                    from_name=from_name
                )
                logger.info("Email service initialized with Brevo as primary provider")
            else:
                logger.info("No HTTP API email provider configured, will use SMTP fallback")
        
        # SMTP fallback (always available if configured)
        if config.EMAIL_ENABLED and config.SMTP_HOST:
            self.fallback_provider = SMTPFallbackProvider(
                host=config.SMTP_HOST,
                port=config.SMTP_PORT,
                user=config.SMTP_USER,
                password=config.SMTP_PASSWORD,
                from_email=from_email,
                from_name=from_name,
                use_tls=config.SMTP_USE_TLS
            )
    
    async def send(self, to_email: str, subject: str, body_text: str,
                   body_html: Optional[str] = None, reply_to: Optional[str] = None,
                   cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> bool:
        """Send email using primary provider, fallback to SMTP if needed."""
        if not to_email:
            return False
        
        # Try primary provider first
        if self.primary_provider:
            success = await self.primary_provider.send(
                to_email, subject, body_text, body_html, reply_to, cc, bcc
            )
            if success:
                return True
        
        # Fallback to SMTP
        if self.fallback_provider:
            return await self.fallback_provider.send(
                to_email, subject, body_text, body_html, reply_to, cc, bcc
            )
        
        logger.warning("No email provider available to send to %s", to_email)
        return False
    
    def set_primary_provider(self, provider: EmailProvider):
        """Dynamically switch primary provider at runtime."""
        self.primary_provider = provider
        logger.info("Primary email provider switched to %s", type(provider).__name__)


# Global email service instance
email_service = EmailService()


# Backward-compatible wrapper functions for existing code
async def send_email(to_email: str, subject: str, body_text: str, 
                     reply_to: str = None, cc: Optional[List[str]] = None, 
                     bcc: Optional[List[str]] = None, body_html: Optional[str] = None) -> bool:
    """Legacy wrapper for backward compatibility."""
    return await email_service.send(to_email, subject, body_text, body_html=body_html, reply_to=reply_to, cc=cc, bcc=bcc)


async def send_handoff_email(owner_email: str, business_name: str, visitor_name: str,
                             visitor_email: str, note: str, conversation_id: str) -> bool:
    subject = f"[{business_name}] A visitor wants to talk to a human"
    lines = [
        f"Someone chatting with your Roviq Ai on {business_name} asked to speak with a person.",
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
    subject = "Welcome to Roviq Ai"
    lines = [
        f"Hi {name or ''},",
        "",
        "Welcome aboard! Your Roviq Ai account is ready. Next step: add a business and "
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


async def send_cancellation_confirmed_email(to_email: str, name: str, business_name: str, 
                                            immediate: bool, access_until: str = None) -> bool:
    subject = f"{business_name}'s subscription is canceled"
    if immediate:
        lines = [f"Hi {name or ''}", "", 
                 f"{business_name} has been moved to the free plan, effective now. "
                 "You can resubscribe any time from Billing."]
    else:
        lines = [f"Hi {name or ''}", "", 
                 f"{business_name}'s subscription is set to cancel. You'll keep your "
                 f"current plan's access until {access_until}, then move to the free plan. "
                 "Changed your mind? You can undo this any time before then from Billing."]
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


async def send_quota_alert_email(to_email: str, name: str, business_name: str, 
                                 threshold: int, used: int, limit: int) -> bool:
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
        "grace period with no interruption to your Roviq Ai while you sort it out -- "
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
        "free plan. Your Roviq Ai is still running, just at the free plan's chat limit. "
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
        f"Your Roviq Ai just booked an appointment on {business_name}.",
        "",
        f"Service: {service}",
        f"When: {start_time}",
        f"Customer: {customer_name}",
        f"Phone: {customer_phone or '(not given)'}",
        f"Email: {customer_email or '(not given)'}",
        f"Reference: {reference}",
    ]
    return await send_email(owner_email, subject, "\n".join(lines), reply_to=customer_email)


async def send_otp_email(to_email: str, otp_code: str, expiry_minutes: int = 10) -> bool:
    """Send OTP for password reset or verification."""
    subject = "Your verification code"
    lines = [
        "Your verification code:",
        "",
        f"  {otp_code}",
        "",
        f"This code expires in {expiry_minutes} minutes.",
        "Do not share this code with anyone.",
        "",
        "If you didn't request this code, you can safely ignore this email.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_sales_welcome_email(to_email: str, name: str, temp_password: str, 
                                   portal_url: str) -> bool:
    """Send welcome email to sales team member with temporary credentials."""
    subject = "Welcome to Roviq AI Sales Portal"
    lines = [
        f"Hi {name or ''},",
        "",
        "Welcome to the Roviq AI Sales Portal! You've been added to our sales team.",
        "",
        "Your temporary login credentials:",
        f"Email: {to_email}",
        f"Temporary Password: {temp_password}",
        "",
        f"Login here: {portal_url}",
        "",
        "IMPORTANT: Please change your password immediately after logging in.",
        "",
        "As a sales team member, you can:",
        "- Onboard new businesses",
        "- Track your referrals and commissions (15% on paid plans)",
        "- View your onboarded businesses",
        "",
        "Commissions are automatically calculated and can be paid out with one click by admins.",
        "",
        "Need help? Reply to this email.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_commission_payout_email(to_email: str, name: str, amount: float, 
                                       business_count: int) -> bool:
    """Send notification when commission is paid out to sales team."""
    subject = "Commission payout processed"
    lines = [
        f"Hi {name or ''},",
        "",
        f"Your commission payout of ₹{amount:.2f} has been processed.",
        "",
        f"This covers {business_count} active paid subscriptions from your referrals.",
        "",
        "Thank you for your continued partnership!",
    ]
    return await send_email(to_email, subject, "\n".join(lines))


async def send_notification_email(to_email: str, title: str, message: str) -> bool:
    """Send in-app notification as email."""
    subject = f"Roviq AI Notification: {title}"
    lines = [
        title,
        "",
        message,
        "",
        "Log in to your dashboard to manage notifications.",
    ]
    return await send_email(to_email, subject, "\n".join(lines))
