"""Subscription lifecycle: proration on plan changes, and immediate vs scheduled plan
changes / cancellation.

This app bills via one-off Razorpay Orders, not Razorpay's separate Subscriptions
product -- see routers/billing.py's module docstring for why (kept intentionally simple,
domestic-only checkout). That means there's no auto-recurring charge to fail and retry.
"Failed payment recovery" here means: remind the owner before their period ends, give them
a grace period of continued paid access if they don't renew in time, and only then
downgrade -- see scheduler.py's billing_lifecycle_job for that scan.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from db import db

PERIOD_DAYS = 30  # a "billing period" is a rolling 30 days from purchase/renewal, not a calendar month


def plan_price_paise(plan: str, plans: dict) -> int:
    return plans[plan]["price_inr"] * 100


def compute_proration(old_plan: str, new_plan: str, period_end_iso: Optional[str], plans: dict) -> int:
    """Amount to charge NOW, in paise, when switching from old_plan to new_plan mid-cycle.
    Positive = charge; negative = credit (applied as a discount on the next invoice --
    Razorpay can't process a negative charge). Zero when there's nothing to prorate: a
    same-price switch, anything involving the free plan (no partial refund for free), or a
    missing/unparseable period end (e.g. a first purchase, nothing to prorate against)."""
    if old_plan == "free" or new_plan == "free" or not period_end_iso:
        return 0
    old_price = plan_price_paise(old_plan, plans)
    new_price = plan_price_paise(new_plan, plans)
    if old_price == new_price:
        return 0
    try:
        period_end = datetime.fromisoformat(period_end_iso)
    except ValueError:
        return 0
    days_remaining = max((period_end - datetime.now(timezone.utc)).days, 0)
    if days_remaining == 0:
        return 0
    return round((new_price - old_price) / PERIOD_DAYS * days_remaining)


async def apply_immediate_plan_change(business_id: str, new_plan: str, new_limit: int):
    """Upgrades (or a same-price lateral switch) take effect right away and reset the
    30-day period from now -- simplest mental model, and the proration charge already
    accounts for the partial period being replaced."""
    now = datetime.now(timezone.utc)
    await db.businesses.update_one({"business_id": business_id}, {"$set": {
        "plan": new_plan, "monthly_limit": new_limit, "subscription_status": "active",
        "current_period_end": (now + timedelta(days=PERIOD_DAYS)).isoformat(),
        "grace_period_ends_at": None, "cancel_at_period_end": False, "pending_plan_change": None,
        "reminder_sent_for_period": None,
    }})


async def schedule_downgrade(business_id: str, new_plan: str):
    """A downgrade takes effect at the end of the CURRENT paid period -- the owner keeps
    what they already paid for instead of losing access to it immediately."""
    await db.businesses.update_one({"business_id": business_id}, {"$set": {"pending_plan_change": new_plan}})


async def cancel_subscription(business_id: str, immediate: bool):
    if immediate:
        from platform_settings import get_plan_limit
        free_limit = await get_plan_limit("free", 100)
        await db.businesses.update_one({"business_id": business_id}, {"$set": {
            "plan": "free", "monthly_limit": free_limit, "subscription_status": "canceled",
            "current_period_end": None, "cancel_at_period_end": False, "pending_plan_change": None,
            "canceled_at": datetime.now(timezone.utc).isoformat(),
        }})
    else:
        await db.businesses.update_one({"business_id": business_id}, {"$set": {"cancel_at_period_end": True}})
