from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import secrets
import urllib.parse

import config
from auth import (
    create_user, authenticate, create_token, get_current_user,
    create_reset_token, create_verify_token, decode_typed_token,
    reset_password as do_reset_password, verify_email as do_verify_email,
    create_mfa_pending_token, verify_totp_code, find_or_create_google_user,
)
from db import db
from ratelimit import limiter
from email_sender import send_email

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=config.IS_PRODUCTION,
        samesite="none" if config.IS_PRODUCTION else "lax",
        path="/",
        max_age=COOKIE_MAX_AGE,
    )


def _frontend_url(path: str) -> str:
    base = (config.FRONTEND_URL or "").rstrip("/")
    return f"{base}{path}" if base else path


async def _send_verification_email(user: dict):
    token = create_verify_token(user["user_id"])
    link = _frontend_url(f"/verify-email?token={token}")
    await send_email(
        user["email"], "Verify your email -- AI Employee",
        f"Hi {user.get('name') or ''},\n\nPlease confirm your email address:\n{link}\n\n"
        "If you didn't create this account, you can ignore this email.",
    )


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
    token = create_token(user["user_id"], user["email"])
    _set_session_cookie(response, token)
    try:
        await _send_verification_email(user)
    except Exception:
        pass  # never block signup on an email provider hiccup
    # NOTE: the raw token is intentionally NOT included in this response body.
    # Storing JWTs in localStorage/JS-reachable storage defeats the point of an
    # httpOnly cookie (any XSS can read localStorage). The cookie set above is
    # sufficient for the SPA; the one deliberate exception is admin impersonation
    # (routers/admin.py), which needs a token the frontend can hand off explicitly.
    return _public_user(user)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginInput, response: Response):
    user = await authenticate(payload.email, payload.password)
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if full and full.get("mfa_enabled"):
        # Password was correct, but a second factor is required before a session
        # is issued -- no session_token cookie is set at this point.
        return {"mfa_required": True, "mfa_token": create_mfa_pending_token(user["user_id"])}
    token = create_token(user["user_id"], user["email"])
    _set_session_cookie(response, token)
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
        raise HTTPException(401, "Incorrect code")
    session = create_token(user["user_id"], user["email"])
    _set_session_cookie(response, session)
    user.pop("_id", None); user.pop("password_hash", None); user.pop("mfa_secret", None)
    return _public_user(user)


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
# to the frontend with the session cookie already set.
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

    session_token = create_token(user["user_id"], user["email"])
    resp = RedirectResponse(_frontend_url("/dashboard"))
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    _set_session_cookie(resp, session_token)
    return resp


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token", path="/")
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
            user["email"], "Reset your password -- AI Employee",
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
    await do_reset_password(payload.token, payload.new_password)
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
