"""Knowledge freshness tracking.

Every place that changes what the AI knows (crawl, manual knowledge, file
upload, chunk edit/delete, quick facts, inventory) calls touch() so the
business doc always has an accurate `knowledge_last_updated_at`. That single
timestamp powers both the dashboard's staleness indicator and the 30-day
nudge email -- one source of truth instead of guessing from scattered
collection timestamps.
"""
from datetime import datetime, timezone, timedelta

from db import db

NUDGE_AFTER_DAYS = 30
NUDGE_COOLDOWN_DAYS = 30  # don't re-nudge more than once per this window


async def touch(business_id: str):
    await db.businesses.update_one(
        {"business_id": business_id},
        {"$set": {"knowledge_last_updated_at": datetime.now(timezone.utc).isoformat()}}
    )


def days_since(iso_timestamp: str) -> int:
    if not iso_timestamp:
        return 9999
    try:
        then = datetime.fromisoformat(iso_timestamp)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).days
    except ValueError:
        return 9999


async def businesses_needing_nudge():
    """Businesses whose knowledge hasn't been touched in NUDGE_AFTER_DAYS, and
    haven't already been nudged within the cooldown window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=NUDGE_AFTER_DAYS)).isoformat()
    cooldown_cutoff = (datetime.now(timezone.utc) - timedelta(days=NUDGE_COOLDOWN_DAYS)).isoformat()
    out = []
    async for biz in db.businesses.find({}, {"_id": 0}):
        last_touch = biz.get("knowledge_last_updated_at") or biz.get("created_at", "")
        last_nudge = biz.get("last_nudge_sent_at")
        if last_touch and last_touch < cutoff and (not last_nudge or last_nudge < cooldown_cutoff):
            out.append(biz)
    return out
