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
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import db
from freshness import businesses_needing_nudge, NUDGE_AFTER_DAYS
from email_sender import send_email
import config

logger = logging.getLogger("roviq-ai.scheduler")

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
                f"Anything changed at {biz['name']}? Your Roviq Ai hasn't heard.",
                f"Hi,\n\nIt's been over {NUDGE_AFTER_DAYS} days since anything was updated in {biz['name']}'s "
                "Roviq Ai knowledge base. If your hours, pricing, stock, or anything else has changed, "
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


async def security_data_cleanup_job():
    """Trims login_events, expired/revoked sessions, and api_key_usage rows so they don't
    grow unbounded. Timestamps here are ISO strings (this codebase's convention throughout),
    not BSON dates, so this uses a lexicographic $lt cutoff instead of a TTL index -- ISO 8601
    strings sort correctly either way."""
    now = datetime.now(timezone.utc)
    login_cutoff = (now - timedelta(days=90)).isoformat()
    session_cutoff = (now - timedelta(days=90)).isoformat()
    usage_cutoff = (now - timedelta(days=30)).isoformat()

    r1 = await db.login_events.delete_many({"created_at": {"$lt": login_cutoff}})
    r2 = await db.sessions.delete_many({"$or": [
        {"revoked_at": {"$ne": None, "$lt": session_cutoff}},
        {"expires_at": {"$lt": session_cutoff}},
    ]})
    r3 = await db.api_key_usage.delete_many({"created_at": {"$lt": usage_cutoff}})
    logger.info("Security data cleanup: %d login events, %d old sessions, %d usage rows removed",
                r1.deleted_count, r2.deleted_count, r3.deleted_count)
    return {"login_events": r1.deleted_count, "sessions": r2.deleted_count, "api_key_usage": r3.deleted_count}


async def embedding_backfill_job():
    """Best-effort weekly pass: embeds any knowledge_chunks missing an `embedding` field --
    created before hybrid search existed, or where the embedding call failed at insert time
    (API hiccup, GEMINI_API_KEY unset at the time). Safe to run repeatedly; only touches
    what's still missing."""
    from retrieval import backfill_embeddings
    total = 0
    async for biz in db.businesses.find({}, {"_id": 0, "business_id": 1}):
        try:
            total += await backfill_embeddings(biz["business_id"])
        except Exception as e:
            logger.warning("Embedding backfill failed for %s: %s", biz["business_id"], e)
    logger.info("Embedding backfill complete: %d chunks embedded", total)
    return total


async def billing_lifecycle_job():
    """Daily scan over every paid business's subscription state -- see subscriptions.py's
    module docstring for why this exists instead of relying on an auto-recurring charge:
    - period ending soon, no reminder sent yet this period -> renewal reminder email
    - period just ended, cancellation/downgrade was requested -> apply it now, no grace period (they asked for this)
    - period just ended, no cancellation requested -> enter a grace period (past_due), "please renew" email
    - grace period elapsed without renewal -> auto-downgrade to free, "moved to free" email
    """
    from platform_settings import get_settings, get_plan_limit
    from routers.billing import PLANS
    from email_sender import send_renewal_reminder_email, send_past_due_email, send_downgraded_email

    settings = await get_settings()
    reminder_days = int(settings.get("renewal_reminder_days_before", 3))
    grace_days = int(settings.get("grace_period_days", 7))
    now = datetime.now(timezone.utc)

    reminded = entered_grace = downgraded = applied_change = 0
    async for biz in db.businesses.find({"plan": {"$ne": "free"}}, {"_id": 0}):
        period_end_iso = biz.get("current_period_end")
        if not period_end_iso:
            continue
        try:
            period_end = datetime.fromisoformat(period_end_iso)
        except ValueError:
            continue
        owner = await db.users.find_one({"user_id": biz["owner_user_id"]}, {"_id": 0, "email": 1, "name": 1})

        if biz.get("subscription_status") == "past_due":
            grace_ends_iso = biz.get("grace_period_ends_at")
            if grace_ends_iso and datetime.fromisoformat(grace_ends_iso) < now:
                free_limit = await get_plan_limit("free", 100)
                await db.businesses.update_one({"business_id": biz["business_id"]}, {"$set": {
                    "plan": "free", "monthly_limit": free_limit, "subscription_status": "canceled",
                    "current_period_end": None, "grace_period_ends_at": None,
                    "canceled_at": now.isoformat(),
                }})
                if owner:
                    await send_downgraded_email(owner["email"], owner.get("name"), biz["name"])
                downgraded += 1
            continue

        if period_end < now:
            target_plan = biz.get("pending_plan_change")
            if biz.get("cancel_at_period_end") or target_plan == "free":
                free_limit = await get_plan_limit("free", 100)
                await db.businesses.update_one({"business_id": biz["business_id"]}, {"$set": {
                    "plan": "free", "monthly_limit": free_limit, "subscription_status": "canceled",
                    "current_period_end": None, "cancel_at_period_end": False, "pending_plan_change": None,
                    "canceled_at": now.isoformat(),
                }})
                downgraded += 1
            elif target_plan and target_plan in PLANS:
                limit = await get_plan_limit(target_plan, PLANS[target_plan]["limit"])
                await db.businesses.update_one({"business_id": biz["business_id"]}, {"$set": {
                    "plan": target_plan, "monthly_limit": limit, "pending_plan_change": None,
                    "current_period_end": (now + timedelta(days=30)).isoformat(),
                }})
                applied_change += 1
            else:
                grace_ends = now + timedelta(days=grace_days)
                await db.businesses.update_one({"business_id": biz["business_id"]}, {"$set": {
                    "subscription_status": "past_due", "grace_period_ends_at": grace_ends.isoformat(),
                }})
                if owner:
                    await send_past_due_email(owner["email"], owner.get("name"), biz["name"], grace_days)
                entered_grace += 1
        elif (period_end - now).days <= reminder_days and biz.get("reminder_sent_for_period") != period_end_iso:
            if owner:
                await send_renewal_reminder_email(owner["email"], owner.get("name"), biz["name"], period_end_iso[:10])
            await db.businesses.update_one({"business_id": biz["business_id"]},
                                           {"$set": {"reminder_sent_for_period": period_end_iso}})
            reminded += 1

    logger.info("Billing lifecycle: %d reminded, %d entered grace, %d downgraded, %d scheduled changes applied",
                reminded, entered_grace, downgraded, applied_change)
    return {"reminded": reminded, "entered_grace": entered_grace, "downgraded": downgraded, "plan_changes_applied": applied_change}


async def plan_snapshot_job():
    """Records today's count of paying (non-free, non-suspended) businesses, keyed by
    month (YYYY-MM). Scheduled just after midnight UTC on the 1st, so each snapshot
    reflects the paying-business count at the start of that month -- the one number
    /admin/churn needs but can't reconstruct after the fact from businesses.created_at
    alone. Upserts on the month key: a manual re-run the same month (e.g. via
    POST /admin/cron/run-plan-snapshot right after deploying this) just refreshes that
    month's count instead of creating a duplicate, so there's no harm in triggering it
    immediately to seed the current month rather than waiting for next month's 1st."""
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")
    paying_count = await db.businesses.count_documents({"plan": {"$ne": "free"}, "status": {"$ne": "suspended"}})
    await db.plan_snapshots.update_one(
        {"_id": month_key},
        {"$set": {"month": month_key, "paying_count": paying_count, "created_at": now.isoformat()}},
        upsert=True,
    )
    logger.info("Plan snapshot for %s: %d paying businesses", month_key, paying_count)
    return {"month": month_key, "paying_count": paying_count}


async def run_weekly_jobs():
    """Entry point usable both by the in-process scheduler and by an external
    cron hitting /admin/cron/run-weekly-jobs directly."""
    recrawled = await weekly_recrawl_job()
    nudged = await staleness_nudge_job()
    cleaned = await security_data_cleanup_job()
    embedded = await embedding_backfill_job()
    return {"recrawled": recrawled, "nudged": nudged, "security_data_cleaned": cleaned, "embeddings_backfilled": embedded}


def start_scheduler():
    global _scheduler
    if not config.ENABLE_SCHEDULER:
        logger.info("In-process scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    if _scheduler is not None and _scheduler.running:
        # Already running -- a second app lifespan cycle in the same process (e.g. two
        # TestClients wrapping the same app in one test) would otherwise leak the first
        # scheduler instance and leave the module global pointing at a second one that a
        # later, unrelated shutdown() call might mistakenly try to stop twice.
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # IntervalTrigger with no start_date runs its first execution one interval
    # (one week) after the job is added -- exactly what we want, so a server
    # restart doesn't trigger an immediate re-crawl of every business.
    _scheduler.add_job(run_weekly_jobs, "interval", weeks=1, id="weekly_jobs", replace_existing=True)
    # Billing lifecycle (renewal reminders, grace periods, auto-downgrade) needs
    # day-granularity, not week-granularity -- a business whose period ends on a Tuesday
    # can't wait until the weekly job happens to run on a Friday to get its grace period.
    _scheduler.add_job(billing_lifecycle_job, "interval", days=1, id="billing_lifecycle", replace_existing=True)
    # Calendar-aligned (cron, not interval) so it always lands on the 1st regardless of
    # when the server happened to start -- an interval trigger would drift to whatever
    # day the process last restarted on.
    _scheduler.add_job(plan_snapshot_job, "cron", day=1, hour=0, minute=10, id="plan_snapshot", replace_existing=True)
    _scheduler.start()
    logger.info("In-process weekly + daily scheduler started")


def stop_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
