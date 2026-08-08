"""Secure password reset and change password functionality using email OTP.

This module implements:
- OTP-based password reset with rate limiting
- Single-use OTPs that expire automatically
- Change password for authenticated users
- Protection against enumeration attacks
"""
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

import config
from db import db
from auth import hash_password, decode_typed_token
from email_service import send_email
from ratelimit import limiter


OTP_TTL_MINUTES = 15
MAX_OTP_ATTEMPTS = 5


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def hash_otp(otp: str) -> str:
    """Hash OTP for secure storage."""
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()


class PasswordResetOTP(BaseModel):
    """Schema for password reset OTP document."""
    otp_id: str
    user_id: str
    email: str
    otp_hash: str
    expires_at: str
    used: bool = False
    attempt_count: int = 0
    created_at: str


async def create_reset_otp(user_id: str, email: str) -> str:
    """Create a new OTP for password reset and send it via email.
    
    Returns the plain OTP (to be sent to user).
    """
    # Invalidate any existing unused OTPs for this user
    await db.password_reset_otps.update_many(
        {"user_id": user_id, "used": False},
        {"$set": {"used": True, "invalidated_reason": "superseded"}}
    )
    
    # Generate OTP
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()
    
    otp_doc = {
        "otp_id": f"otp_{secrets.token_urlsafe(12)}",
        "user_id": user_id,
        "email": email,
        "otp_hash": otp_hash,
        "expires_at": expires_at,
        "used": False,
        "attempt_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.password_reset_otps.insert_one(otp_doc)
    
    # Send OTP via email
    subject = "Your Roviq AI Password Reset Code"
    body_text = f"""Hi,

Someone requested a password reset for your Roviq AI account. 
Use the following code to reset your password (valid for {OTP_TTL_MINUTES} minutes):

{otp}

If you didn't request this, you can ignore this email and your password will remain unchanged.

For security reasons:
- This code can only be used once
- Do not share this code with anyone
- Our support team will never ask for this code
"""
    
    try:
        await send_email(email, subject, body_text)
    except Exception as e:
        # Log error but don't fail - we don't want to leak whether email exists
        pass
    
    return otp


async def verify_reset_otp(email: str, otp: str) -> Optional[dict]:
    """Verify OTP and return user info if valid.
    
    Returns None if invalid (to prevent enumeration).
    Implements rate limiting on attempts.
    """
    from auth import decode_token
    
    # Find user by email first (prevents enumeration)
    user = await db.users.find_one({"email": email.strip().lower()})
    if not user:
        # Still wait to prevent timing attacks
        await asyncio.sleep(0.1)
        return None
    
    user_id = user["user_id"]
    
    # Find active OTP
    otp_doc = await db.password_reset_otps.find_one({
        "user_id": user_id,
        "used": False,
        "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}
    })
    
    if not otp_doc:
        return None
    
    # Check attempt limit
    if otp_doc.get("attempt_count", 0) >= MAX_OTP_ATTEMPTS:
        # Mark as exhausted
        await db.password_reset_otps.update_one(
            {"otp_id": otp_doc["otp_id"]},
            {"$set": {"used": True, "invalidated_reason": "max_attempts_exceeded"}}
        )
        return None
    
    # Increment attempt count
    await db.password_reset_otps.update_one(
        {"otp_id": otp_doc["otp_id"]},
        {"$inc": {"attempt_count": 1}}
    )
    
    # Verify OTP
    otp_hash = hash_otp(otp)
    if otp_hash != otp_doc["otp_hash"]:
        return None
    
    # Mark as used
    await db.password_reset_otps.update_one(
        {"otp_id": otp_doc["otp_id"]},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return user


async def reset_password_with_otp(email: str, otp: str, new_password: str) -> str:
    """Reset password using OTP verification.
    
    Returns user_id on success.
    Raises HTTPException on failure.
    """
    import asyncio
    
    user = await verify_reset_otp(email, otp)
    if not user:
        raise HTTPException(400, "Invalid or expired code")
    
    # Update password
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
            "failed_login_count": 0,
            "locked_until": None
        }}
    )
    
    # Revoke all sessions for security
    import sessions as sessions_lib
    await sessions_lib.revoke_all_sessions(user["user_id"], reason="password_reset")
    
    return user["user_id"]


async def request_password_reset(email: str) -> bool:
    """Request a password reset OTP.
    
    Always returns True to prevent email enumeration.
    """
    user = await db.users.find_one({"email": email.strip().lower()})
    if not user:
        # Still return success to prevent enumeration
        return True
    
    try:
        await create_reset_otp(user["user_id"], user["email"])
    except Exception:
        pass  # Don't leak errors
    
    return True


class ChangePasswordInput(BaseModel):
    """Input model for changing password when authenticated."""
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


async def change_password(user_id: str, current_password: str, new_password: str) -> bool:
    """Change password for authenticated user.
    
    Verifies current password before allowing change.
    """
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(404, "User not found")
    
    # Google-only accounts can't change password this way
    if not user.get("password_hash"):
        raise HTTPException(400, "Please use email verification to set a password")
    
    # Verify current password
    from auth import verify_password
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    
    # Update password
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Optionally revoke other sessions (keep current)
    # This forces re-login on all devices
    import sessions as sessions_lib
    await sessions_lib.revoke_all_sessions(user_id, except_session_id=None, reason="password_change")
    
    return True


class ChangePasswordWithOTPInput(BaseModel):
    """Input model for changing password with OTP verification."""
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=8, max_length=200)


async def change_password_with_otp(email: str, otp: str, new_password: str) -> str:
    """Alternative password change flow using OTP (for users who forgot current password)."""
    return await reset_password_with_otp(email, otp, new_password)


# Rate-limited endpoints will be defined in routers/auth.py
