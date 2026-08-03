"""Platform-wide tunable settings, configured by an admin at /admin/settings.

Previously these existed only as an admin UI with a DEFAULT_SETTINGS dict in
routers/admin.py -- the values were saved to Mongo but nothing outside the
admin panel ever read them back, so e.g. changing "confidence threshold" or
"max upload size" in the admin UI silently did nothing. This module is the
one place that reads them, so every consumer (chat, knowledge uploads,
crawling, plan limits) sees the same live values admins actually configured.
"""
from db import db

DEFAULTS = {
    "default_free_limit": 100,
    "starter_limit": 2000,
    "pro_limit": 10000,  # legacy -- "pro" was renamed to "growth" with the same limit; kept so any
                          # business record still holding plan="pro" (or an admin override already
                          # set against this key) keeps resolving correctly.
    "growth_limit": 10000,
    "scale_limit": 25000,
    "referral_discount_pct": 25,
    "referral_months": 12,
    "confidence_threshold": 0.6,
    "max_upload_mb": 15,
    "crawl_max_pages": 15,
    "watermark_required_on_free": True,
    "maintenance_mode": False,
    "max_failed_login_attempts": 5,
    "lockout_minutes": 15,
    "refresh_token_ttl_days": 30,
    "api_key_default_rate_limit_per_min": 60,
    # GST (India). gst_rate is a percentage (18.0 = 18%). Verify hsn_sac_code and rate with
    # your CA before going live -- this is a billing calculation, not tax advice.
    "gst_enabled": True,
    "gst_rate": 18.0,
    "hsn_sac_code": "998314",
    "seller_legal_name": "",
    "seller_gstin": "",
    "seller_state_code": "27",  # Maharashtra; change to match your actual GST registration
    "seller_address": "",
    # Subscription lifecycle: how long a past-due business keeps paid-plan access before
    # being auto-downgraded to free, and how many days before period end to send a renewal
    # reminder (there's no auto-recurring charge -- see routers/billing.py's docstring).
    "grace_period_days": 7,
    "renewal_reminder_days_before": 3,
    # Overage billing: OFF by default (safer -- no owner is surprised by a charge they
    # didn't opt into). When enabled, usage past monthly_limit is tracked and billed as a
    # separate line item at the next renewal instead of hard-blocking the chat widget.
    "overage_billing_enabled": False,
    "overage_rate_per_chat_paise": 50,
    "support_email": "",
    "company_legal_name": "",
    "company_address": "",
}

_PLAN_LIMIT_KEYS = {"free": "default_free_limit", "starter": "starter_limit", "pro": "pro_limit",
                     "growth": "growth_limit", "scale": "scale_limit"}


async def get_settings() -> dict:
    doc = await db.platform_settings.find_one({"_id": "singleton"})
    if not doc:
        return dict(DEFAULTS)
    doc.pop("_id", None)
    return {**DEFAULTS, **doc}


async def get_plan_limit(plan: str, fallback: int) -> int:
    """The effective monthly chat limit for a plan, honoring an admin override
    if one has been set, otherwise the plan's built-in default."""
    key = _PLAN_LIMIT_KEYS.get(plan)
    if not key:
        return fallback
    settings = await get_settings()
    try:
        return int(settings.get(key, fallback))
    except (TypeError, ValueError):
        return fallback
