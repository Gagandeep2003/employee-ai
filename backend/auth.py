"""Email + password authentication. JWT-based, no third-party auth branding.

Several distinct JWT "types" are issued from here, all signed with the same
JWT_SECRET but never interchangeable -- get_current_user only ever accepts
type == "access", so a leaked password-reset or email-verify link (even though
both are short-lived) can never be replayed as a login session.
"""
import uuid
import bcrypt
import jwt
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import Cookie, Header, HTTPException, Request
from typing import Optional

import config
from db import db

JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 60 * 24 * 7      # 7 days (single-token session)
RESET_TTL_MIN = 30                # password reset links expire quickly
VERIFY_TTL_MIN = 60 * 24          # email verification links last a day
MFA_PENDING_TTL_MIN = 10          # window between "password OK" and "TOTP code OK"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _encode(payload: dict) -> str:
    return jwt.encode(payload, config.JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_token(user_id: str, email: str) -> str:
    return _encode({
        "sub": user_id, "email": email, "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    })


def create_reset_token(user_id: str) -> str:
    return _encode({
        "sub": user_id, "type": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    })


def create_verify_token(user_id: str) -> str:
    return _encode({
        "sub": user_id, "type": "email_verify",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=VERIFY_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    })


def create_mfa_pending_token(user_id: str) -> str:
    return _encode({
        "sub": user_id, "type": "mfa_pending",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=MFA_PENDING_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    })


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.JWT_SECRET, algorithms=[JWT_ALGORITHM])


def decode_typed_token(token: str, expected_type: str) -> dict:
    """Decodes a token and rejects it unless its `type` claim matches exactly --
    this is what stops a password-reset link from working as a login session,
    or a login session from working as a password-reset link."""
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "This link has expired -- please request a new one")
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid or malformed link")
    if payload.get("type") != expected_type:
        raise HTTPException(400, "Invalid link")
    return payload


async def find_or_create_google_user(email: str, name: str, picture: Optional[str], google_id: str) -> dict:
    """Google already verified this email, so accounts created/linked this way
    start out email_verified=True. If a password-based account with the same
    email already exists, we link google_id onto it rather than creating a
    duplicate -- the owner can then sign in with either method."""
    email = email.strip().lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        updates = {"google_id": google_id}
        if not existing.get("email_verified"):
            updates["email_verified"] = True
        if not existing.get("picture") and picture:
            updates["picture"] = picture
        await db.users.update_one({"email": email}, {"$set": updates})
        existing = await db.users.find_one({"email": email})
        existing.pop("_id", None); existing.pop("password_hash", None); existing.pop("mfa_secret", None)
        return existing

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "password_hash": None,  # Google-only account; can set one later via forgot-password
        "name": name or email.split("@")[0],
        "picture": picture,
        "role": "owner",
        "disabled": False,
        "email_verified": True,
        "mfa_enabled": False,
        "mfa_secret": None,
        "google_id": google_id,
        "referral_code": f"ref_{uuid.uuid4().hex[:8]}",
        "referred_by_code": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None); doc.pop("password_hash", None); doc.pop("mfa_secret", None)
    return doc


async def create_user(email: str, password: str, name: str, referral_code: Optional[str] = None) -> dict:
    email = email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    ref = f"ref_{uuid.uuid4().hex[:8]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "password_hash": hash_password(password),
        "name": name or email.split("@")[0],
        "picture": None,
        "role": "owner",
        "disabled": False,
        "email_verified": False,
        "mfa_enabled": False,
        "mfa_secret": None,
        "referral_code": ref,
        "referred_by_code": referral_code,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    if referral_code:
        await db.referrals.insert_one({
            "id": str(uuid.uuid4()),
            "code": referral_code,
            "referred_user_id": user_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    doc.pop("mfa_secret", None)
    return doc


async def authenticate(email: str, password: str) -> dict:
    email = email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash"):
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if user.get("disabled"):
        raise HTTPException(403, "This account has been disabled")
    user.pop("_id", None)
    user.pop("password_hash", None)
    user.pop("mfa_secret", None)
    return user


async def get_current_user(request: Request,
                           session_token: Optional[str] = Cookie(None),
                           authorization: Optional[str] = Header(None)) -> dict:
    token = session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")
    if payload.get("type") != "access":
        # e.g. someone tries to use a password-reset or MFA-pending token as a session
        raise HTTPException(status_code=401, detail="Invalid session")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0, "mfa_secret": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return user


async def reset_password(token: str, new_password: str):
    payload = decode_typed_token(token, "password_reset")
    user = await db.users.find_one({"user_id": payload["sub"]})
    if not user:
        raise HTTPException(400, "Invalid link")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"password_hash": hash_password(new_password)}})


async def verify_email(token: str):
    payload = decode_typed_token(token, "email_verify")
    res = await db.users.update_one({"user_id": payload["sub"]}, {"$set": {"email_verified": True}})
    if res.matched_count == 0:
        raise HTTPException(400, "Invalid link")


def generate_mfa_secret() -> str:
    import pyotp
    return pyotp.random_base32()


def mfa_provisioning_uri(secret: str, email: str) -> str:
    import pyotp
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=config.APP_NAME)


def verify_totp_code(secret: str, code: str) -> bool:
    import pyotp
    try:
        return pyotp.totp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


def generate_backup_code() -> str:
    return secrets.token_hex(4).upper()


async def seed_admin():
    """Idempotent admin seed from env. This is the ONLY way a user becomes an admin
    at bootstrap time -- there is no implicit 'first user' fallback, because that would
    let anyone who signs up first on a misconfigured deployment grant themselves
    full platform access."""
    if not config.ADMIN_EMAIL or not config.ADMIN_PASSWORD:
        _warn_no_admin_seed()
        return
    email = config.ADMIN_EMAIL
    pw = config.ADMIN_PASSWORD
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": email,
            "password_hash": hash_password(pw),
            "name": "Admin",
            "picture": None,
            "role": "admin",
            "disabled": False,
            "email_verified": True,
            "mfa_enabled": False,
            "mfa_secret": None,
            "referral_code": f"ref_{uuid.uuid4().hex[:8]}",
            "referred_by_code": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        updates = {}
        if not verify_password(pw, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(pw)
        if existing.get("role") != "admin":
            updates["role"] = "admin"
        if updates:
            await db.users.update_one({"email": email}, {"$set": updates})


def _warn_no_admin_seed():
    import logging
    logging.getLogger("ai-employee.auth").warning(
        "ADMIN_EMAIL/ADMIN_PASSWORD not set -- no admin account will be seeded. "
        "Set both env vars and restart to create one; promote further admins from the admin panel."
    )
