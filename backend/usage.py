"""Monthly usage-period rollover.

The free/starter/pro plans are metered per calendar month (`monthly_used` vs
`monthly_limit`), but nothing previously reset `monthly_used` when a new month
started — a business that hit its limit stayed locked out forever until an
admin manually reset it. This module fixes that with a lazy rollover: every
time a business's usage is read or incremented, we check whether the stored
`usage_period` still matches the current month and reset if not. No cron job
or scheduler needed, which keeps this free to run on any host.
"""
from datetime import datetime, timezone

from db import db


def current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def ensure_current_period(biz: dict) -> dict:
    """Return `biz` with monthly_used rolled over if the billing month changed.
    Also persists the reset to Mongo so subsequent reads are consistent."""
    period = current_period()
    if biz.get("usage_period") != period:
        await db.businesses.update_one(
            {"business_id": biz["business_id"]},
            {"$set": {"usage_period": period, "monthly_used": 0}},
        )
        biz = {**biz, "usage_period": period, "monthly_used": 0}
    return biz
