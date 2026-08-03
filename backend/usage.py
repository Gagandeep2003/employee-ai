"""Monthly usage-period rollover, and configurable overage billing.

The free/starter/pro plans are metered per calendar month (`monthly_used` vs
`monthly_limit`), but nothing previously reset `monthly_used` when a new month
started — a business that hit its limit stayed locked out forever until an
admin manually reset it. This module fixes that with a lazy rollover: every
time a business's usage is read or incremented, we check whether the stored
`usage_period` still matches the current month and reset if not. No cron job
or scheduler needed, which keeps this free to run on any host.

Overage billing (off by default) piggybacks on the same rollover point: if a business
accumulated chats past its monthly_limit last period (see routers/chat.py, which only
tracks these instead of hard-blocking when overage_billing_enabled is on), a real
GST-numbered invoice is generated for the overage, marked "due" -- this app has no stored
payment method to auto-charge, so it's collected at the business's next plan purchase.
"""
import logging
from datetime import datetime, timezone

from db import db

logger = logging.getLogger("ai-employee.usage")


def current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def ensure_current_period(biz: dict) -> dict:
    """Return `biz` with monthly_used rolled over if the billing month changed.
    Also persists the reset to Mongo so subsequent reads are consistent."""
    period = current_period()
    if biz.get("usage_period") != period:
        prev_overage = biz.get("overage_count", 0)
        updates = {"usage_period": period, "monthly_used": 0, "overage_count": 0, "quota_alerts_sent": []}
        await db.businesses.update_one({"business_id": biz["business_id"]}, {"$set": updates})
        biz = {**biz, **updates}
        if prev_overage > 0:
            await _bill_overage(biz, prev_overage)
    return biz


QUOTA_ALERT_THRESHOLDS = [75, 90, 100]


async def maybe_send_quota_alert(biz: dict, new_used: int):
    """Fires an email the first time usage crosses 75%/90%/100% of the plan limit each
    period -- each threshold sends at most once (tracked via quota_alerts_sent, reset on
    rollover), so a burst of chats right at the limit doesn't spam three emails at once
    for thresholds crossed simultaneously, nor repeat the same one on every later chat."""
    limit = biz.get("monthly_limit", 100)
    if limit <= 0:
        return
    pct = (new_used / limit) * 100
    already_sent = set(biz.get("quota_alerts_sent") or [])
    crossed = [t for t in QUOTA_ALERT_THRESHOLDS if pct >= t and t not in already_sent]
    if not crossed:
        return
    threshold = max(crossed)  # only the highest newly-crossed threshold needs an email
    await db.businesses.update_one({"business_id": biz["business_id"]},
                                   {"$set": {"quota_alerts_sent": sorted(already_sent | set(crossed))}})
    owner = await db.users.find_one({"user_id": biz["owner_user_id"]}, {"_id": 0, "email": 1, "name": 1})
    if not owner:
        return
    from email_sender import send_quota_alert_email
    try:
        await send_quota_alert_email(owner["email"], owner.get("name"), biz["name"], threshold, new_used, limit)
    except Exception as e:
        logger.warning("Quota alert email failed for %s: %s", biz["business_id"], e)


async def _bill_overage(biz: dict, overage_count: int):
    from platform_settings import get_settings
    settings = await get_settings()
    if not settings.get("overage_billing_enabled", False):
        return
    rate = int(settings.get("overage_rate_per_chat_paise", 50))
    amount_paise = overage_count * rate
    if amount_paise <= 0 or biz.get("plan") == "free":  # no overage billing on the free plan -- nothing to compare against
        return
    import invoicing
    try:
        inv = await invoicing.create_invoice(
            biz["business_id"], biz["owner_user_id"], biz.get("plan", "free"), amount_paise,
            description=f"Overage: {overage_count} chats beyond your monthly plan limit", status="due",
        )
        user = await db.users.find_one({"user_id": biz["owner_user_id"]}, {"_id": 0})
        if user:
            from email_sender import send_email
            await send_email(
                user["email"], f"Overage charge for {biz['name']}",
                f"Hi {user.get('name') or ''},\n\n{biz['name']} used {overage_count} chats beyond its monthly "
                f"plan limit last period. An invoice for Rs. {amount_paise / 100:,.2f} ({inv['invoice_number']}) "
                "has been added to your account and will be included with your next plan renewal.",
            )
    except Exception as e:
        logger.warning("Overage invoicing failed for %s: %s", biz["business_id"], e)


async def outstanding_due_paise(business_id: str) -> int:
    """Total of any unpaid overage invoices -- folded into the amount charged at the
    business's next plan purchase (see routers/billing.py's subscribe())."""
    total = 0
    async for inv in db.invoices.find({"business_id": business_id, "status": "due"}, {"_id": 0, "total_paise": 1}):
        total += inv.get("total_paise", 0)
    return total


async def mark_due_invoices_paid(business_id: str, razorpay_payment_id: str):
    await db.invoices.update_many(
        {"business_id": business_id, "status": "due"},
        {"$set": {"status": "paid", "razorpay_payment_id": razorpay_payment_id}},
    )
