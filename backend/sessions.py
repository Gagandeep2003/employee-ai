"""Session & device management for the refresh-token auth model.

A "session" (db.sessions) is created once per successful login (password, MFA-verified,
or Google OAuth) and represents one device/browser. Its refresh token is opaque and
rotated on every use via /auth/refresh; only the current hash is valid, but the
immediately-previous hash is kept for one rotation cycle so a replayed, already-superseded
token is recognized as token theft (see rotate_refresh_token) and the session is revoked
on the spot instead of silently accepted.

This module also owns login history (db.login_events) and the security-posture summary
shown on the owner's Security page -- kept together because they all read/write the same
two collections and are always displayed side by side.
"""
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from db import db
from auth import generate_opaque_token, hash_token, create_token
from platform_settings import get_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def client_ip(request) -> Optional[str]:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# Device labeling -- simple regex parse for display only (e.g. "Chrome on macOS").
# Not a fingerprinting mechanism and not used for any security decision beyond
# "have we seen a device with this label for this user before".
# ---------------------------------------------------------------------------
_UA_BROWSER = [
    (re.compile(r"Edg/"), "Edge"),
    (re.compile(r"OPR/|Opera"), "Opera"),
    (re.compile(r"CriOS/"), "Chrome (iOS)"),
    (re.compile(r"FxiOS/"), "Firefox (iOS)"),
    (re.compile(r"Chrome/"), "Chrome"),
    (re.compile(r"Firefox/"), "Firefox"),
    (re.compile(r"Version/.*Safari/"), "Safari"),
]
_UA_OS = [
    (re.compile(r"iPhone|iPad|iPod"), "iOS"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"Windows"), "Windows"),
    (re.compile(r"Mac OS X"), "macOS"),
    (re.compile(r"Linux"), "Linux"),
]


def describe_device(user_agent: Optional[str]) -> str:
    ua = user_agent or ""
    browser = next((name for pat, name in _UA_BROWSER if pat.search(ua)), None)
    osname = next((name for pat, name in _UA_OS if pat.search(ua)), None)
    if browser and osname:
        return f"{browser} on {osname}"
    return browser or osname or "Unknown device"


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------
async def create_session(user_id: str, email: str, request) -> tuple:
    """Creates a new device/session record for a just-authenticated user. Returns
    (session_id, access_token, refresh_token). Call exactly once per login (password,
    MFA-verified, or Google OAuth) -- not on every request."""
    settings = await get_settings()
    ttl_days = int(settings.get("refresh_token_ttl_days", 30))
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    refresh_token = generate_opaque_token()
    now = _now_iso()
    ua = request.headers.get("user-agent") if request else None
    await db.sessions.insert_one({
        "id": session_id,
        "user_id": user_id,
        "refresh_token_hash": hash_token(refresh_token),
        "prev_refresh_token_hash": None,
        "device_name": describe_device(ua),
        "user_agent": ua,
        "ip": client_ip(request),
        "created_at": now,
        "last_used_at": now,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat(),
        "revoked_at": None,
        "revoked_reason": None,
    })
    access_token = create_token(user_id, email, session_id=session_id)
    return session_id, access_token, refresh_token


class RefreshTokenInvalid(Exception):
    """Missing, unknown, expired, or already-revoked refresh token -- caller should
    treat this as a normal logged-out state and ask for a fresh login."""


class RefreshTokenReused(Exception):
    """An already-rotated-away refresh token was presented again -- a strong signal the
    token was stolen and used from two places. The session has already been revoked by
    the time this is raised; the caller should surface a "please sign in again" state."""


async def rotate_refresh_token(raw_token: str, request) -> tuple:
    """Validates and rotates a refresh token. Returns (session_id, user_id, new_access_token,
    new_refresh_token). Raises RefreshTokenInvalid / RefreshTokenReused on failure."""
    if not raw_token:
        raise RefreshTokenInvalid()
    token_hash = hash_token(raw_token)
    session = await db.sessions.find_one({"refresh_token_hash": token_hash, "revoked_at": None})
    if not session:
        reused = await db.sessions.find_one({"prev_refresh_token_hash": token_hash, "revoked_at": None})
        if reused:
            await revoke_session(reused["id"], reason="reuse_detected")
            raise RefreshTokenReused()
        raise RefreshTokenInvalid()
    if session["expires_at"] < _now_iso():
        await revoke_session(session["id"], reason="expired")
        raise RefreshTokenInvalid()

    new_refresh = generate_opaque_token()
    await db.sessions.update_one({"id": session["id"]}, {"$set": {
        "refresh_token_hash": hash_token(new_refresh),
        "prev_refresh_token_hash": token_hash,
        "last_used_at": _now_iso(),
        "ip": client_ip(request) or session.get("ip"),
    }})
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "email": 1, "disabled": 1})
    if not user or user.get("disabled"):
        await revoke_session(session["id"], reason="account_disabled")
        raise RefreshTokenInvalid()
    new_access = create_token(session["user_id"], user["email"], session_id=session["id"])
    return session["id"], session["user_id"], new_access, new_refresh


async def revoke_session(session_id: str, reason: str = "user"):
    await db.sessions.update_one({"id": session_id, "revoked_at": None},
                                  {"$set": {"revoked_at": _now_iso(), "revoked_reason": reason}})


async def revoke_all_sessions(user_id: str, except_session_id: Optional[str] = None, reason: str = "user") -> int:
    query = {"user_id": user_id, "revoked_at": None}
    if except_session_id:
        query["id"] = {"$ne": except_session_id}
    res = await db.sessions.update_many(query, {"$set": {"revoked_at": _now_iso(), "revoked_reason": reason}})
    return res.modified_count


async def list_sessions(user_id: str, current_session_id: Optional[str] = None) -> list:
    now = _now_iso()
    items = await db.sessions.find(
        {"user_id": user_id, "revoked_at": None, "expires_at": {"$gt": now}},
        {"_id": 0, "refresh_token_hash": 0, "prev_refresh_token_hash": 0},
    ).sort("last_used_at", -1).to_list(100)
    for it in items:
        it["current"] = bool(current_session_id) and it["id"] == current_session_id
    return items


async def is_new_device(user_id: str, device_name: str) -> bool:
    """Whether we have never seen this device label for this user before -- checked
    against every session ever created (not just active ones), so a device that logged
    out and back in isn't treated as new every time. Used only to decide whether to send
    a "new sign-in" security email, never to block a login."""
    prior = await db.sessions.count_documents({"user_id": user_id, "device_name": device_name})
    return prior == 0


# ---------------------------------------------------------------------------
# Login history
# ---------------------------------------------------------------------------
async def record_login_event(request, user_id: Optional[str], email: str, outcome: str, method: str = "password"):
    """outcome: success | failed_password | locked | mfa_required | mfa_failed | mfa_success"""
    ua = request.headers.get("user-agent") if request else None
    await db.login_events.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "email": (email or "").strip().lower(),
        "outcome": outcome,
        "method": method,
        "ip": client_ip(request),
        "user_agent": ua,
        "device_name": describe_device(ua),
        "created_at": _now_iso(),
    })


async def list_login_history(user_id: str, limit: int = 25) -> list:
    return await db.login_events.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)


# ---------------------------------------------------------------------------
# Security Center overview
# ---------------------------------------------------------------------------
async def security_overview(user_id: str) -> dict:
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0, "mfa_secret": 0})
    if not user:
        return {}
    now = _now_iso()
    active_sessions = await db.sessions.count_documents({"user_id": user_id, "revoked_at": None, "expires_at": {"$gt": now}})
    active_api_keys = await db.api_keys.count_documents({"owner_user_id": user_id, "status": "active"})
    recent_logins = await list_login_history(user_id, limit=5)

    pw_changed = user.get("password_changed_at")
    pw_recent = False
    if pw_changed:
        try:
            pw_recent = (datetime.now(timezone.utc) - datetime.fromisoformat(pw_changed)).days < 365
        except ValueError:
            pw_recent = False

    checklist = [
        {"key": "mfa", "label": "Two-factor authentication enabled", "ok": bool(user.get("mfa_enabled"))},
        {"key": "email_verified", "label": "Email address verified", "ok": bool(user.get("email_verified"))},
        {"key": "password_age", "label": "Password changed within the last year", "ok": pw_recent},
        {"key": "session_hygiene", "label": "5 or fewer active sessions", "ok": active_sessions <= 5},
    ]
    score = round(100 * sum(1 for c in checklist if c["ok"]) / len(checklist))

    return {
        "mfa_enabled": bool(user.get("mfa_enabled")),
        "email_verified": bool(user.get("email_verified")),
        "password_changed_at": pw_changed,
        "active_sessions": active_sessions,
        "active_api_keys": active_api_keys,
        "recent_logins": recent_logins,
        "checklist": checklist,
        "score": score,
    }
