"""Central configuration & startup validation.

All environment variables are read here, once, so the app fails fast with a
clear error message at startup instead of failing confusingly on the first
request that happens to touch a missing var. Nothing in this file talks to
the network or the database — it only reads os.environ.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("ai-employee.config")

ENV = os.environ.get("ENV", "development").strip().lower()  # development | production
IS_PRODUCTION = ENV == "production"


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        _fail(f"Missing required environment variable: {name}")
    return val


def _fail(message: str):
    logger.error(message)
    # Fail fast and loud — a half-configured app in production is worse than one that won't boot.
    raise RuntimeError(message)


# ---------------------------------------------------------------------------
# Core / database
# ---------------------------------------------------------------------------
MONGO_URL = _require("MONGO_URL")
DB_NAME = _require("DB_NAME")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
JWT_SECRET = _require("JWT_SECRET")
if IS_PRODUCTION and (len(JWT_SECRET) < 32 or JWT_SECRET.lower() in {"changeme", "secret", "dev-secret"}):
    _fail("JWT_SECRET is too short/weak for production. Use at least 32 random characters, "
          "e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`.")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower() or None
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip() or None
if IS_PRODUCTION and ADMIN_PASSWORD and len(ADMIN_PASSWORD) < 10:
    _fail("ADMIN_PASSWORD is too short for production (use 10+ characters).")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_cors_raw = os.environ.get("CORS_ORIGINS", "").strip()
if IS_PRODUCTION and (not _cors_raw or _cors_raw == "*"):
    _fail("CORS_ORIGINS must be an explicit comma-separated list of allowed origins in production "
          "(wildcard '*' is not allowed together with credentialed cookies).")
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["http://localhost:3000"]

# ---------------------------------------------------------------------------
# LLM (Gemini, direct — no third-party proxy)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() or None
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
if IS_PRODUCTION and not GEMINI_API_KEY:
    _fail("GEMINI_API_KEY is required in production (get one at https://aistudio.google.com/apikey).")

# ---------------------------------------------------------------------------
# Object storage (S3-compatible: AWS S3, Cloudflare R2, Backblaze B2, MinIO...)
# Falls back to local disk storage when unset, which is fine for a single-instance
# / lowest-cost deployment but will NOT survive redeploys on most PaaS hosts.
# ---------------------------------------------------------------------------
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "").strip() or None
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip() or None
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip() or None
S3_REGION = os.environ.get("S3_REGION", "auto").strip()
S3_PUBLIC_URL = os.environ.get("S3_PUBLIC_URL", "").strip() or None
STORAGE_LOCAL_DIR = os.environ.get("STORAGE_LOCAL_DIR", str(ROOT_DIR / "uploads")).strip()
USE_S3_STORAGE = bool(S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY and S3_BUCKET)
if IS_PRODUCTION and not USE_S3_STORAGE:
    logger.warning(
        "No S3-compatible storage configured — falling back to local disk at %s. "
        "Uploaded files will NOT survive a redeploy on most hosting platforms. "
        "Set S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY / S3_BUCKET (Cloudflare R2's free tier "
        "is a good low-cost option) before going live.", STORAGE_LOCAL_DIR,
    )

# ---------------------------------------------------------------------------
# Razorpay (domestic/INR payments)
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "").strip() or None
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "").strip() or None
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip() or None
RAZORPAY_ENABLED = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
if IS_PRODUCTION and not RAZORPAY_ENABLED:
    logger.warning("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — paid plan checkout will be disabled "
                    "(the Free plan will still work).")

# ---------------------------------------------------------------------------
# Rate limiting (in-memory by default; set REDIS_URL for multi-instance deployments)
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "").strip() or None

# ---------------------------------------------------------------------------
# Outbound email (handoff notifications to business owners). Works with any
# SMTP provider -- Resend, Brevo, AWS SES, Gmail (app password), etc. -- so
# there's no vendor lock-in. Free tiers: Resend (3k/mo), Brevo (300/day).
# ---------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip() or None
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip() or None
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip() or None
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "").strip() or None
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "AI Employee").strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() != "false"
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL)
if IS_PRODUCTION and not EMAIL_ENABLED:
    logger.warning("SMTP_* not fully configured -- human handoff notifications will only "
                    "appear in-app, no email will be sent to business owners.")

# ---------------------------------------------------------------------------
# Google OAuth (optional "Continue with Google" on signup/login)
# Requires an OAuth 2.0 Client ID from Google Cloud Console, with
# GOOGLE_REDIRECT_URI added as an authorized redirect URI there. That's an
# external setup step only you can do -- see DEPLOYMENT.md.
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip() or None
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip() or None
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip() or None
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)

# ---------------------------------------------------------------------------
# Scheduled jobs (weekly re-crawl + staleness nudges)
# ---------------------------------------------------------------------------
ENABLE_SCHEDULER = os.environ.get("ENABLE_SCHEDULER", "true").strip().lower() != "false"

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
APP_NAME = os.environ.get("APP_NAME", "ai-employee").strip()
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip() or None

logger.info("Config loaded: ENV=%s GEMINI_MODEL=%s S3_STORAGE=%s RAZORPAY=%s REDIS=%s",
            ENV, GEMINI_MODEL, USE_S3_STORAGE, RAZORPAY_ENABLED, bool(REDIS_URL))
