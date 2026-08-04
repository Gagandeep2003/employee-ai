"""Email + password authentication. JWT-based, no third-party auth branding.

Several distinct JWT "types" are issued from here, all signed with the same
JWT_SECRET but never interchangeable -- get_current_user only ever accepts
type == "access", so a leaked password-reset or email-verify link (even though
both are short-lived) can never be replayed as a login session.

Session model (refresh-token rotation): a login issues two things --
1. an `access` JWT (short-lived, ACCESS_TTL_MIN, carries a `sid` session-id
   claim), sent as before in the `session_token` cookie and used for every
   authenticated request via get_current_user.
2. an opaque, cryptographically random refresh token (NOT a JWT -- so it can
   be revoked before its own expiry, unlike a self-contained token), sent in
   a `refresh_token` cookie scoped to `/api/auth` only. Only its SHA-256 hash
   is ever stored server-side, in a `sessions` document that also carries
   device/IP metadata. See sessions.py for issuance, rotation-with-reuse-
   detection, and revocation.
"""
import uuid
import bcrypt
import jwt
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import Cookie, Header, HTTPException, Request
from typing import Optional

import config
from db import db

JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 30               # short-lived; the refresh token (see sessions.py) keeps the user signed in
RESET_TTL_MIN = 30                # password reset links expire quickly
VERIFY_TTL_MIN = 60 * 24          # email verification links last a day
MFA_PENDING_TTL_MIN = 10          # window between "password OK" and "TOTP code OK"


def generate_opaque_token(nbytes: int = 32) -> str:
    """A cryptographically random, non-JWT token -- used for refresh tokens and API keys,
    where we need server-side revocation before the token's own natural expiry (a self-
    contained JWT can't be un-issued once handed out)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 of an opaque token. Only this hash is ever stored -- the raw token is shown
    to the user exactly once (at issuance) and is unrecoverable after that, same model as
    GitHub/Stripe API keys."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _encode(payload: dict) -> str:
    return jwt.encode(payload, config.JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_token(user_id: str, email: str, session_id: Optional[str] = None) -> str:
    payload = {
        "sub": user_id, "email": email, "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    }
    if session_id:
        payload["sid"] = session_id
    return _encode(payload)


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
        "password_changed_at": None,
        "failed_login_count": 0,
        "locked_until": None,
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
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
        "failed_login_count": 0,
        "locked_until": None,
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
    from platform_settings import get_settings  # local import: avoids a module-load-order cycle with db-backed settings
    email = email.strip().lower()
    user = await db.users.find_one({"email": email})

    locked_until = (user or {}).get("locked_until")
    if locked_until and locked_until > datetime.now(timezone.utc).isoformat():
        raise HTTPException(423, "Too many failed attempts -- this account is temporarily locked. Try again later "
                                  "or use 'forgot password' to reset it.")

    if not user or not user.get("password_hash") or not verify_password(password, user["password_hash"]):
        if user:
            settings = await get_settings()
            max_attempts = int(settings.get("max_failed_login_attempts", 5))
            lockout_minutes = int(settings.get("lockout_minutes", 15))
            failed = int(user.get("failed_login_count", 0)) + 1
            updates = {"failed_login_count": failed}
            if failed >= max_attempts:
                updates["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)).isoformat()
                updates["failed_login_count"] = 0
            await db.users.update_one({"email": email}, {"$set": updates})
        raise HTTPException(401, "Invalid email or password")

    if user.get("disabled"):
        raise HTTPException(403, "This account has been disabled")

    if user.get("failed_login_count") or user.get("locked_until"):
        await db.users.update_one({"email": email}, {"$set": {"failed_login_count": 0, "locked_until": None}})

    user.pop("_id", None)
    user.pop("password_hash", None)
    user.pop("mfa_secret", None)
    return user


def _bearer_or_cookie(session_token: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if session_token:
        return session_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    return None


async def get_current_user(request: Request,
                           session_token: Optional[str] = Cookie(None),
                           authorization: Optional[str] = Header(None)) -> dict:
    token = _bearer_or_cookie(session_token, authorization)
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
    sid = payload.get("sid")
    if sid:
        # Enforces revocation (single-device revoke, revoke-all, or the automatic
        # revoke-all-other-sessions on password reset) immediately, rather than letting an
        # already-issued access token keep working until its own TTL happens to expire.
        session = await db.sessions.find_one({"id": sid}, {"_id": 0, "revoked_at": 1})
        if session and session.get("revoked_at"):
            raise HTTPException(status_code=401, detail="This session was signed out")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0, "mfa_secret": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return user


async def get_current_session_id(session_token: Optional[str] = Cookie(None),
                                 authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Best-effort: returns the sid claim from the caller's access token, or None (e.g. an
    older token issued before session tracking existed, or an impersonation bearer token
    that never had a session of its own). Never raises -- callers use this only to decide
    which row in a list is "this device", not to authenticate."""
    token = _bearer_or_cookie(session_token, authorization)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None
    return payload.get("sid")


async def reset_password(token: str, new_password: str) -> str:
    payload = decode_typed_token(token, "password_reset")
    user = await db.users.find_one({"user_id": payload["sub"]})
    if not user:
        raise HTTPException(400, "Invalid link")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {
        "password_hash": hash_password(new_password),
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
        "failed_login_count": 0,
        "locked_until": None,
    }})
    return user["user_id"]


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


async def mfa_setup_for(user_id: str, email: str) -> dict:
    """Step 1 of enabling 2FA: generate a secret and return its provisioning URI. Stored but
    NOT enabled until mfa_enable_for confirms a valid code -- otherwise a dropped connection
    mid-setup could silently brick the account's login."""
    secret = generate_mfa_secret()
    await db.users.update_one({"user_id": user_id}, {"$set": {"mfa_secret": secret, "mfa_enabled": False}})
    return {"secret": secret, "provisioning_uri": mfa_provisioning_uri(secret, email)}


async def mfa_enable_for(user_id: str, code: str):
    user = await db.users.find_one({"user_id": user_id})
    if not user or not user.get("mfa_secret"):
        raise HTTPException(400, "Call /mfa/setup first")
    if not verify_totp_code(user["mfa_secret"], code):
        raise HTTPException(401, "Incorrect code -- check your authenticator app and try again")
    await db.users.update_one({"user_id": user_id}, {"$set": {"mfa_enabled": True}})


async def mfa_disable_for(user_id: str, password: str):
    user = await db.users.find_one({"user_id": user_id})
    if not user or not verify_password(password, user.get("password_hash") or ""):
        raise HTTPException(401, "Incorrect password")
    await db.users.update_one({"user_id": user_id}, {"$set": {"mfa_enabled": False, "mfa_secret": None}})


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
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
            "failed_login_count": 0,
            "locked_until": None,
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
    logging.getLogger("roviq-ai.auth").warning(
        "ADMIN_EMAIL/ADMIN_PASSWORD not set -- no admin account will be seeded. "
        "Set both env vars and restart to create one; promote further admins from the admin panel."
    )
