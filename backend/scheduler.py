"""Scheduled jobs: weekly re-crawl + staleness nudges.

Runs in-process via APScheduler by default -- zero extra infrastructure,
which fits a single-instance deployment (the default in DEPLOYMENT.md).
If you run more than one backend replica, each one would otherwise run
these jobs independently and duplicate work (and duplicate nudge emails) --
set ENABLE_SCHEDULER=false on all but one replica, or disable it everywhere
and hit /admin/cron/run-weekly-jobs from an external cron instead (e.g. a
GitHub Actions scheduled workflow, or your host's cron feature).
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import db
from freshness import businesses_needing_nudge, NUDGE_AFTER_DAYS
from email_sender import send_email
import config

logger = logging.getLogger("ai-employee.scheduler")

_scheduler = None


async def weekly_recrawl_job():
    """Re-crawls every business that has a website set. Sequential with a small
    delay between each, to avoid hammering either the target sites or the
    Gemini API (snapshot regeneration) all at once."""
    from routers.businesses import _run_crawl  # local import avoids a circular import at module load

    count = 0
    async for biz in db.businesses.find({"website": {"$exists": True, "$ne": None}}, {"_id": 0, "business_id": 1, "website": 1}):
        if not biz.get("website"):
            continue
        try:
            await _run_crawl(biz["business_id"], biz["website"])
            count += 1
        except Exception as e:
            logger.warning("Scheduled re-crawl failed for %s: %s", biz["business_id"], e)
        await asyncio.sleep(2)  # be polite to target sites / spread out LLM calls
    logger.info("Weekly re-crawl complete: %d businesses", count)
    return count


async def staleness_nudge_job():
    """Emails owners whose knowledge hasn't been touched in NUDGE_AFTER_DAYS days."""
    stale = await businesses_needing_nudge()
    sent = 0
    for biz in stale:
        if not biz.get("email"):
            continue
        try:
            await send_email(
                biz["email"],
                f"Anything changed at {biz['name']}? Your AI Employee hasn't heard.",
                f"Hi,\n\nIt's been over {NUDGE_AFTER_DAYS} days since anything was updated in {biz['name']}'s "
                "AI Employee knowledge base. If your hours, pricing, stock, or anything else has changed, "
                "now's a good time to update it -- even a quick note in Quick Facts takes 10 seconds and "
                "keeps your AI from giving customers outdated answers.\n\n"
                "Log in to your dashboard to update it.",
            )
            await db.businesses.update_one(
                {"business_id": biz["business_id"]},
                {"$set": {"last_nudge_sent_at": datetime.now(timezone.utc).isoformat()}}
            )
            sent += 1
        except Exception as e:
            logger.warning("Nudge email failed for %s: %s", biz["business_id"], e)
    logger.info("Staleness nudge job complete: %d emails sent", sent)
    return sent


async def run_weekly_jobs():
    """Entry point usable both by the in-process scheduler and by an external
    cron hitting /admin/cron/run-weekly-jobs directly."""
    recrawled = await weekly_recrawl_job()
    nudged = await staleness_nudge_job()
    return {"recrawled": recrawled, "nudged": nudged}


def start_scheduler():
    global _scheduler
    if not config.ENABLE_SCHEDULER:
        logger.info("In-process scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # IntervalTrigger with no start_date runs its first execution one interval
    # (one week) after the job is added -- exactly what we want, so a server
    # restart doesn't trigger an immediate re-crawl of every business.
    _scheduler.add_job(run_weekly_jobs, "interval", weeks=1, id="weekly_jobs")
    _scheduler.start()
    logger.info("In-process weekly scheduler started")


def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)
