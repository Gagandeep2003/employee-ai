from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import secrets
import urllib.parse

import config
from auth import (
    create_user, authenticate, create_token, get_current_user, get_current_session_id,
    ACCESS_TTL_MIN,
    create_reset_token, create_verify_token, decode_typed_token,
    reset_password as do_reset_password, verify_email as do_verify_email,
    create_mfa_pending_token, verify_totp_code, find_or_create_google_user,
    mfa_setup_for, mfa_enable_for, mfa_disable_for,
)
import sessions as sessions_lib
from db import db
from ratelimit import limiter
from email_sender import send_email, send_new_device_login_email, send_welcome_email
import password_reset

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE_MAX_AGE = ACCESS_TTL_MIN * 60
# The refresh cookie's browser-side max-age is just an upper bound / convenience for the
# browser to stop sending an obviously-dead cookie -- the *authoritative* expiry is the
# session document's expires_at (admin-tunable via platform_settings.refresh_token_ttl_days),
# checked server-side on every /auth/refresh call.
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 60
REFRESH_COOKIE_PATH = "/api/auth"


def _set_access_cookie(response: Response, token: str):
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=config.IS_PRODUCTION,
        samesite="none" if config.IS_PRODUCTION else "lax",
        path="/",
        max_age=ACCESS_COOKIE_MAX_AGE,
    )


def _set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=config.IS_PRODUCTION,
        samesite="none" if config.IS_PRODUCTION else "lax",
        path=REFRESH_COOKIE_PATH,
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def _clear_auth_cookies(response: Response):
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH)


def _frontend_url(path: str) -> str:
    base = (config.FRONTEND_URL or "").rstrip("/")
    return f"{base}{path}" if base else path


async def _send_verification_email(user: dict):
    token = create_verify_token(user["user_id"])
    link = _frontend_url(f"/verify-email?token={token}")
    await send_email(
        user["email"], "Verify your email -- Roviq Ai",
        f"Hi {user.get('name') or ''},\n\nPlease confirm your email address:\n{link}\n\n"
        "If you didn't create this account, you can ignore this email.",
    )


async def _finish_login(response: Response, request: Request, user: dict, method: str = "password") -> str:
    """Common tail of every flow that ends in an issued session (password login,
    MFA-verified login, Google OAuth): creates a session/device record, sets both
    cookies, records the login event, and fires a new-device alert email if this
    device has never been seen for this user before. Returns the new session id."""
    ua = request.headers.get("user-agent") if request else None
    device_name = sessions_lib.describe_device(ua)
    is_new = await sessions_lib.is_new_device(user["user_id"], device_name)

    session_id, access_token, refresh_token = await sessions_lib.create_session(user["user_id"], user["email"], request)
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)
    await sessions_lib.record_login_event(request, user["user_id"], user["email"], "success", method=method)

    if is_new:
        try:
            await send_new_device_login_email(
                user["email"], user.get("name"), device_name,
                sessions_lib.client_ip(request), sessions_lib._now_iso(),
            )
        except Exception:
            pass  # never block login on an email provider hiccup
    return session_id


class SignupInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    referral_code: Optional[str] = None


class LoginInput(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
@limiter.limit("10/hour")
async def signup(request: Request, payload: SignupInput, response: Response):
    user = await create_user(payload.email, payload.password, payload.name, payload.referral_code)
    await _finish_login(response, request, user, method="password")
    try:
        await _send_verification_email(user)
        await send_welcome_email(user["email"], user.get("name"))
    except Exception:
        pass  # never block signup on an email provider hiccup
    # NOTE: the raw token is intentionally NOT included in this response body.
    # Storing JWTs in localStorage/JS-reachable storage defeats the point of an
    # httpOnly cookie (any XSS can read localStorage). The cookies set above are
    # sufficient for the SPA; the one deliberate exception is admin impersonation
    # (routers/admin.py), which needs a token the frontend can hand off explicitly.
    return _public_user(user)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginInput, response: Response):
    try:
        user = await authenticate(payload.email, payload.password)
    except HTTPException as e:
        outcome = "locked" if e.status_code == 423 else "failed_password"
        existing = await db.users.find_one({"email": payload.email.strip().lower()}, {"_id": 0, "user_id": 1})
        await sessions_lib.record_login_event(request, existing["user_id"] if existing else None,
                                              payload.email, outcome, method="password")
        raise
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if full and full.get("mfa_enabled"):
        # Password was correct, but a second factor is required before a session
        # is issued -- no cookies are set at this point.
        await sessions_lib.record_login_event(request, user["user_id"], user["email"], "mfa_required", method="password")
        return {"mfa_required": True, "mfa_token": create_mfa_pending_token(user["user_id"])}
    await _finish_login(response, request, user, method="password")
    return _public_user(user)


class MfaVerifyInput(BaseModel):
    mfa_token: str
    code: str


@router.post("/mfa/verify")
@limiter.limit("10/minute")
async def mfa_verify(request: Request, payload: MfaVerifyInput, response: Response):
    token_payload = decode_typed_token(payload.mfa_token, "mfa_pending")
    user = await db.users.find_one({"user_id": token_payload["sub"]})
    if not user or not user.get("mfa_enabled") or not user.get("mfa_secret"):
        raise HTTPException(400, "MFA is not enabled on this account")
    if not verify_totp_code(user["mfa_secret"], payload.code):
        await sessions_lib.record_login_event(request, user["user_id"], user["email"], "mfa_failed", method="mfa")
        raise HTTPException(401, "Incorrect code")
    user.pop("_id", None); user.pop("password_hash", None); user.pop("mfa_secret", None)
    await _finish_login(response, request, user, method="mfa")
    return _public_user(user)


# ---------------------------------------------------------------------------
# Refresh-token rotation & session/device management
# ---------------------------------------------------------------------------
@router.post("/refresh")
@limiter.limit("60/minute")
async def refresh(request: Request, response: Response, refresh_token: Optional[str] = None):
    from fastapi import Cookie
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(401, "No refresh token")
    try:
        session_id, user_id, access_token, new_refresh = await sessions_lib.rotate_refresh_token(raw, request)
    except sessions_lib.RefreshTokenReused:
        # Token theft signal: the session is already revoked by rotate_refresh_token.
        # Force a clean re-login on this device rather than silently issuing a new pair.
        _clear_auth_cookies(response)
        raise HTTPException(401, "This session was invalidated for security reasons -- please sign in again")
    except sessions_lib.RefreshTokenInvalid:
        _clear_auth_cookies(response)
        raise HTTPException(401, "Session expired -- please sign in again")
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, new_refresh)
    return {"ok": True}


@router.get("/sessions")
async def list_sessions(user=Depends(get_current_user), current_sid: Optional[str] = Depends(get_current_session_id)):
    return await sessions_lib.list_sessions(user["user_id"], current_sid)


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, response: Response, user=Depends(get_current_user),
                         current_sid: Optional[str] = Depends(get_current_session_id)):
    session = await db.sessions.find_one({"id": session_id, "user_id": user["user_id"]})
    if not session:
        raise HTTPException(404, "Session not found")
    await sessions_lib.revoke_session(session_id, reason="user")
    if session_id == current_sid:
        _clear_auth_cookies(response)
    return {"ok": True, "was_current_device": session_id == current_sid}


class RevokeAllInput(BaseModel):
    include_current: bool = False


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(payload: RevokeAllInput, response: Response, user=Depends(get_current_user),
                              current_sid: Optional[str] = Depends(get_current_session_id)):
    except_sid = None if payload.include_current else current_sid
    count = await sessions_lib.revoke_all_sessions(user["user_id"], except_session_id=except_sid, reason="user")
    if payload.include_current:
        _clear_auth_cookies(response)
    return {"ok": True, "revoked": count}


@router.get("/login-history")
async def login_history(user=Depends(get_current_user)):
    return await sessions_lib.list_login_history(user["user_id"])


@router.get("/security-overview")
async def security_overview(user=Depends(get_current_user)):
    return await sessions_lib.security_overview(user["user_id"])


# ---------------------------------------------------------------------------
# Two-factor authentication (TOTP) -- available to every account, not just admins.
# Impersonation makes admin accounts especially high-value, but any owner's account
# is a real target too (billing, customer data, the widget on their live site).
# ---------------------------------------------------------------------------
@router.post("/mfa/setup")
@limiter.limit("10/hour")
async def auth_mfa_setup(request: Request, user=Depends(get_current_user)):
    return await mfa_setup_for(user["user_id"], user["email"])


class AuthMfaEnableIn(BaseModel):
    code: str


@router.post("/mfa/enable")
@limiter.limit("10/hour")
async def auth_mfa_enable(request: Request, payload: AuthMfaEnableIn, user=Depends(get_current_user)):
    await mfa_enable_for(user["user_id"], payload.code)
    return {"ok": True}


class AuthMfaDisableIn(BaseModel):
    password: str


@router.post("/mfa/disable")
@limiter.limit("10/hour")
async def auth_mfa_disable(request: Request, payload: AuthMfaDisableIn, user=Depends(get_current_user)):
    await mfa_disable_for(user["user_id"], payload.password)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Google OAuth ("Continue with Google"). Only active when GOOGLE_CLIENT_ID /
# GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI are set -- see DEPLOYMENT.md for
# the Google Cloud Console setup this requires (an external step; a real
# OAuth client can't be created for you from here).
#
# Flow: browser hits /google/login (full-page redirect, not an XHR) -> we
# redirect to Google with a random `state` also stashed in a short-lived
# cookie -> Google redirects back to /google/callback -> we check the cookie
# matches the returned state (CSRF protection for the flow), exchange the
# code for a token, fetch the profile, find-or-create the user, and redirect
# to the frontend with the session cookies already set.
# ---------------------------------------------------------------------------
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_STATE_COOKIE = "oauth_state"


@router.get("/google/login")
@limiter.limit("20/minute")
async def google_login(request: Request):
    if not config.GOOGLE_OAUTH_ENABLED:
        raise HTTPException(503, "Google sign-in is not configured on this deployment")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    redirect = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE, value=state, httponly=True,
        secure=config.IS_PRODUCTION, samesite="lax", path="/", max_age=600,
    )
    return redirect


@router.get("/google/callback")
@limiter.limit("20/minute")
async def google_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if not config.GOOGLE_OAUTH_ENABLED:
        raise HTTPException(503, "Google sign-in is not configured on this deployment")
    if error:
        return RedirectResponse(_frontend_url(f"/login?error={urllib.parse.quote(error)}"))

    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not cookie_state or state != cookie_state:
        return RedirectResponse(_frontend_url("/login?error=oauth_state_mismatch"))

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }) as resp:
            if resp.status != 200:
                return RedirectResponse(_frontend_url("/login?error=google_token_exchange_failed"))
            token_data = await resp.json()

        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse(_frontend_url("/login?error=google_token_exchange_failed"))

        async with session.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}) as resp:
            if resp.status != 200:
                return RedirectResponse(_frontend_url("/login?error=google_profile_fetch_failed"))
            profile = await resp.json()

    email = profile.get("email")
    if not email or not profile.get("email_verified", True):
        return RedirectResponse(_frontend_url("/login?error=google_email_unverified"))

    user = await find_or_create_google_user(
        email=email, name=profile.get("name") or "", picture=profile.get("picture"),
        google_id=profile.get("sub", ""),
    )

    if user.get("mfa_enabled"):
        mfa_token = create_mfa_pending_token(user["user_id"])
        resp = RedirectResponse(_frontend_url(f"/login?mfa_token={mfa_token}"))
        resp.delete_cookie(OAUTH_STATE_COOKIE, path="/")
        return resp

    # Admin accounts have no business of their own -- send them straight to the admin
    # console instead of the owner dashboard (see the matching fix in Login.jsx).
    resp = RedirectResponse(_frontend_url("/admin" if user.get("role") == "admin" else "/dashboard"))
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    await _finish_login(resp, request, user, method="google")
    return resp


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.post("/logout")
async def logout(response: Response, request: Request, current_sid: Optional[str] = Depends(get_current_session_id)):
    if current_sid:
        await sessions_lib.revoke_session(current_sid, reason="logout")
    _clear_auth_cookies(response)
    return {"ok": True}


class ForgotPasswordInput(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
@limiter.limit("5/hour")
async def forgot_password(request: Request, payload: ForgotPasswordInput):
    user = await db.users.find_one({"email": payload.email.strip().lower()})
    if user:
        link = _frontend_url(f"/reset-password?token={create_reset_token(user['user_id'])}")
        await send_email(
            user["email"], "Reset your password -- Roviq Ai",
            f"Hi {user.get('name') or ''},\n\nSomeone requested a password reset for this account. "
            f"If that was you, set a new password here (link expires in 30 minutes):\n{link}\n\n"
            "If you didn't request this, you can safely ignore this email.",
        )
    # Always return the same response whether or not the email exists -- otherwise
    # this endpoint becomes a way to enumerate registered email addresses.
    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/reset-password")
@limiter.limit("10/hour")
async def reset_password_endpoint(request: Request, payload: ResetPasswordInput):
    user_id = await do_reset_password(payload.token, payload.new_password)
    # A password reset is exactly the moment to assume the account may have been
    # compromised (or the owner is deliberately locking out a stolen session) --
    # kill every other device's session so the new password is the only way back in.
    await sessions_lib.revoke_all_sessions(user_id, reason="password_reset")
    return {"ok": True}


class VerifyEmailInput(BaseModel):
    token: str


@router.post("/verify-email")
@limiter.limit("20/hour")
async def verify_email_endpoint(request: Request, payload: VerifyEmailInput):
    await do_verify_email(payload.token)
    return {"ok": True}


@router.post("/verify-email/resend")
@limiter.limit("5/hour")
async def resend_verification(request: Request, user: dict = Depends(get_current_user)):
    if user.get("email_verified"):
        return {"ok": True, "message": "Already verified"}
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    await _send_verification_email(full)
    return {"ok": True}


def _public_user(user: dict) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "referral_code": user["referral_code"],
        "role": user.get("role", "owner"),
        "email_verified": bool(user.get("email_verified", False)),
        "mfa_enabled": bool(user.get("mfa_enabled", False)),
    }
    async def get_current_admin_user(request: Request,
                                 session_token: Optional[str] = Cookie(None),
                                 authorization: Optional[str] = Header(None)) -> dict:
    """Requires authenticated user with admin role"""
    user = await get_current_user(request, session_token, authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
