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
    "pro_limit": 10000,
    "referral_discount_pct": 25,
    "referral_months": 12,
    "confidence_threshold": 0.6,
    "max_upload_mb": 15,
    "crawl_max_pages": 15,
    "watermark_required_on_free": True,
    "maintenance_mode": False,
}

_PLAN_LIMIT_KEYS = {"free": "default_free_limit", "starter": "starter_limit", "pro": "pro_limit"}


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
