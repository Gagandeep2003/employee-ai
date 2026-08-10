from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid

from auth import get_current_user, create_token
from db import db
from audit import log as audit_log
from routers.billing import PLANS
from auth import get_current_admin_user  # Or wherever it is defined
from retrieval import invalidate
import config
from platform_settings import get_plan_limit

router = APIRouter(prefix="/admin", tags=["admin"])

# Rough cost-per-chat-turn estimate for the admin dashboards below. Based on
# gemini-3.1-flash-lite pricing (~$0.25/M input, ~$1.50/M output tokens) and an
# assumed ~900 input tokens (system prompt + RAG context + short history) plus
# ~250 output tokens per turn. This is a budgeting estimate, not a billing
# reconciliation -- check your Google AI Studio / Cloud Billing console for
# actual spend. Update these constants if you change GEMINI_MODEL.
EST_INPUT_TOKENS_PER_MSG = 900
EST_OUTPUT_TOKENS_PER_MSG = 250
EST_INPUT_USD_PER_M = 0.25
EST_OUTPUT_USD_PER_M = 1.50
EST_COST_PER_MSG_USD = (EST_INPUT_TOKENS_PER_MSG / 1_000_000 * EST_INPUT_USD_PER_M
                        + EST_OUTPUT_TOKENS_PER_MSG / 1_000_000 * EST_OUTPUT_USD_PER_M)


# ---------- Auth guard ----------
async def _ensure_admin(user: dict):
    """Admin access requires role == 'admin', set only via ADMIN_EMAIL/ADMIN_PASSWORD
    seeding at startup or by an existing admin promoting another user. There is
    deliberately NO "first user is admin" fallback: on a public-signup app that
    would let anyone who registers first (e.g. because ADMIN_EMAIL was never set)
    grant themselves full platform access."""
    if user.get("role") == "admin":
        return
    raise HTTPException(403, "Admin only")


# =====================================================================
# ADMIN MFA (TOTP) -- impersonation makes admin accounts high-value targets,
# so this is available to every admin and strongly recommended immediately
# after first login. Not force-enabled (that would risk locking out the
# freshly-seeded admin before they've had a chance to set it up).
# =====================================================================
@router.post("/mfa/setup")
async def mfa_setup(user=Depends(get_current_user)):
    await _ensure_admin(user)
    from auth import mfa_setup_for
    return await mfa_setup_for(user["user_id"], user["email"])


class MfaEnableIn(BaseModel):
    code: str


@router.post("/mfa/enable")
async def mfa_enable(payload: MfaEnableIn, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    from auth import mfa_enable_for
    await mfa_enable_for(user["user_id"], payload.code)
    await audit_log(request, user["user_id"], "admin.mfa_enabled", "user", user["user_id"], {})
    return {"ok": True}


class MfaDisableIn(BaseModel):
    password: str


@router.post("/mfa/disable")
async def mfa_disable(payload: MfaDisableIn, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    from auth import mfa_disable_for
    await mfa_disable_for(user["user_id"], payload.password)
    await audit_log(request, user["user_id"], "admin.mfa_disabled", "user", user["user_id"], {})
    return {"ok": True}


# =====================================================================
# EXECUTIVE DASHBOARD
# =====================================================================
@router.get("/overview")
async def overview(request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)

    users_total = await db.users.count_documents({})
    users_owners = await db.users.count_documents({"role": "owner"})
    businesses_total = await db.businesses.count_documents({})
    biz_free = await db.businesses.count_documents({"plan": "free"})
    biz_paid = await db.businesses.count_documents({"plan": {"$ne": "free"}})
    biz_suspended = await db.businesses.count_documents({"status": "suspended"})

    conversations = await db.conversations.count_documents({})
    messages = await db.messages.count_documents({})

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat()
    today_conv = await db.conversations.count_documents({"created_at": {"$gte": today_start}})
    today_msgs = await db.messages.count_documents({"created_at": {"$gte": today_start}})

    # Revenue
    invoices_paid = await db.invoices.find({"status": "paid"}, {"_id": 0}).to_list(5000)
    revenue_total = sum(i.get("amount_inr", 0) for i in invoices_paid)
    revenue_today = sum(i.get("amount_inr", 0) for i in invoices_paid if i.get("created_at", "") >= today_start)

    # MRR = sum of monthly plan prices for active paid businesses
    mrr = 0
    async for b in db.businesses.find({"plan": {"$ne": "free"}, "status": {"$ne": "suspended"}}, {"plan": 1, "_id": 0}):
        mrr += PLANS.get(b["plan"], {}).get("price_inr", 0)
    arr = mrr * 12

    # AI cost estimate -- see EST_COST_PER_MSG_USD above for the pricing basis.
    ai_cost_today_usd = round(today_msgs * EST_COST_PER_MSG_USD, 4)

    # System health — quick checks
    try:
        await db.command("ping")
        db_health = "healthy"
    except Exception:
        db_health = "down"

    kb_chunks = await db.knowledge_chunks.count_documents({})
    files = await db.files.count_documents({})
    active_crawls = await db.businesses.count_documents({"crawl_status": "crawling"})
    open_tickets = await db.notifications.count_documents({"type": "handoff", "read": False})

    return {
        "users": {"total": users_total, "owners": users_owners},
        "businesses": {"total": businesses_total, "free": biz_free, "paid": biz_paid, "suspended": biz_suspended},
        "revenue": {"mrr_inr": mrr, "arr_inr": arr, "today_inr": revenue_today, "total_inr": revenue_total, "invoices_paid": len(invoices_paid)},
        "ai": {"conversations_all": conversations, "messages_all": messages, "conversations_today": today_conv, "messages_today": today_msgs, "estimated_cost_today_usd": ai_cost_today_usd},
        "knowledge": {"chunks": kb_chunks, "files": files, "active_crawls": active_crawls},
        "support": {"open_tickets": open_tickets},
        "system": {"db": db_health, "backend": "healthy", "version": "1.0.0"},
    }


@router.get("/growth")
async def growth(months: int = 6, format: Optional[str] = None, user=Depends(get_current_user)):
    """New signups and new paid conversions per month, plus month-over-month growth %."""
    await _ensure_admin(user)
    months = max(1, min(months, 24))
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(months - 1, -1, -1):
        # compute the i-th month back from the current month, robust to month-length differences
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
        new_signups = await db.businesses.count_documents({"created_at": {"$gte": start.isoformat(), "$lt": end.isoformat()}})
        new_invoices = await db.invoices.find(
            {"status": "paid", "document_type": {"$ne": "credit_note"},
             "created_at": {"$gte": start.isoformat(), "$lt": end.isoformat()}},
            {"_id": 0, "business_id": 1},
        ).to_list(2000)
        new_paying_businesses = len({inv["business_id"] for inv in new_invoices})
        rows.append({"month": start.strftime("%Y-%m"), "new_signups": new_signups, "new_paying_businesses": new_paying_businesses})

    for idx, row in enumerate(rows):
        prev = rows[idx - 1]["new_signups"] if idx > 0 else None
        row["signup_growth_pct"] = round((row["new_signups"] - prev) / prev * 100, 1) if prev else None

    if format:
        from exports import export_response
        columns = [("month", "Month"), ("new_signups", "New Signups"),
                  ("new_paying_businesses", "New Paying Businesses"), ("signup_growth_pct", "MoM Growth %")]
        return export_response(format, rows, columns, "growth", "Growth Report")
    return rows


@router.get("/churn")
async def churn(months: int = 6, format: Optional[str] = None, user=Depends(get_current_user)):
    """Monthly churn rate: businesses that canceled a paid plan during the month, divided by
    businesses that were actually on a paid plan at the start of it.

    That denominator comes from plan_snapshots when a snapshot exists for the month (see
    scheduler.plan_snapshot_job, taken on the 1st of each month) -- an exact paying-cohort
    count, not an estimate. For months before this snapshot existed, there's no way to
    reconstruct historical plan state after the fact, so those rows fall back to the old
    approximation (total signups before that date, which overcounts the denominator since it
    includes businesses that were never on a paid plan). Each row says which method it used
    in denominator_source so this doesn't quietly look more precise than it is; the trend
    across months is meaningful either way, but only snapshot-backed rows are exact."""
    await _ensure_admin(user)
    months = max(1, min(months, 24))
    now = datetime.now(timezone.utc)
    month_starts = []
    for i in range(months - 1, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_starts.append(datetime(year, month, 1, tzinfo=timezone.utc))

    month_keys = [s.strftime("%Y-%m") for s in month_starts]
    snapshots = {s["_id"]: s async for s in db.plan_snapshots.find({"_id": {"$in": month_keys}})}

    rows = []
    for start in month_starts:
        month_key = start.strftime("%Y-%m")
        end = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc) if start.month == 12 else datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)
        canceled = await db.businesses.count_documents({"canceled_at": {"$gte": start.isoformat(), "$lt": end.isoformat()}})
        snap = snapshots.get(month_key)
        if snap:
            existing_at_start = snap["paying_count"]
            source = "snapshot"
        else:
            existing_at_start = await db.businesses.count_documents({"created_at": {"$lt": start.isoformat()}})
            source = "approximation"
        rate = round(canceled / existing_at_start * 100, 2) if existing_at_start else 0.0
        rows.append({"month": month_key, "canceled": canceled, "existing_at_start": existing_at_start,
                     "churn_rate_pct": rate, "denominator_source": source})

    if format:
        from exports import export_response
        columns = [("month", "Month"), ("canceled", "Canceled"), ("existing_at_start", "Existing at Start"),
                  ("churn_rate_pct", "Churn Rate %"), ("denominator_source", "Denominator Source")]
        return export_response(format, rows, columns, "churn", "Churn Report")
    return rows


@router.get("/revenue-timeseries")
async def revenue_timeseries(days: int = 30, user=Depends(get_current_user)):
    await _ensure_admin(user)
    now = datetime.now(timezone.utc)
    out = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        end = (datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
        docs = await db.invoices.find({"status": "paid", "created_at": {"$gte": start, "$lt": end}}, {"_id": 0, "amount_inr": 1}).to_list(1000)
        conv = await db.conversations.count_documents({"created_at": {"$gte": start, "$lt": end}})
        out.append({"date": day.isoformat(), "revenue_inr": sum(d.get("amount_inr", 0) for d in docs), "conversations": conv})
    return out


# =====================================================================
# BUSINESSES
# =====================================================================
def _health_score(biz: dict, kb_chunks: int, conversations: int) -> dict:
    """A simple, transparent customer health score (0-100) combining engagement, setup
    completeness, and payment status -- not a black box. Each factor is visible in the
    breakdown so an admin can see *why* a business scored the way it did, not just the number."""
    factors = []
    usage_ratio = (biz.get("monthly_used", 0) / biz.get("monthly_limit", 100)) if biz.get("monthly_limit") else 0
    engaged = 0 < usage_ratio < 1.5  # actively used, not completely idle, not wildly over (may signal churn-risk frustration)
    factors.append(("Actively chatting", engaged))
    factors.append(("Knowledge base set up", kb_chunks >= 3))
    factors.append(("Has real conversations", conversations >= 1))
    factors.append(("Payment in good standing", biz.get("subscription_status", "active") == "active"))
    factors.append(("On a paid plan", biz.get("plan", "free") != "free"))
    score = round(100 * sum(1 for _, ok in factors if ok) / len(factors))
    return {"score": score, "factors": [{"label": l, "ok": ok} for l, ok in factors]}


@router.get("/businesses")
async def list_businesses(q: Optional[str] = None, plan: Optional[str] = None, format: Optional[str] = None,
                          user=Depends(get_current_user)):
    await _ensure_admin(user)
    query: dict = {}
    if plan: query["plan"] = plan
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"country": {"$regex": q, "$options": "i"}},
            {"business_id": q},
        ]
    items = await db.businesses.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # attach owner info + health score
    for b in items:
        owner = await db.users.find_one({"user_id": b.get("owner_user_id")}, {"_id": 0, "email": 1, "name": 1})
        b["owner_email"] = owner.get("email") if owner else None
        b["owner_name"] = owner.get("name") if owner else None
        b["kb_chunks"] = await db.knowledge_chunks.count_documents({"business_id": b["business_id"]})
        b["conversations"] = await db.conversations.count_documents({"business_id": b["business_id"]})
        b["health"] = _health_score(b, b["kb_chunks"], b["conversations"])["score"]

    if format:
        from exports import export_response
        columns = [
            ("name", "Business"), ("owner_email", "Owner Email"), ("plan", "Plan"),
            ("subscription_status", "Status"), ("monthly_used", "Chats Used"), ("monthly_limit", "Chat Limit"),
            ("kb_chunks", "Knowledge Chunks"), ("conversations", "Conversations"), ("health", "Health Score"),
            ("country", "Country"), ("created_at", "Signed Up"),
        ]
        return export_response(format, items, columns, "businesses", "Businesses Report")
    return items


@router.get("/businesses/{bid}")
async def business_detail(bid: str, user=Depends(get_current_user)):
    await _ensure_admin(user)
    b = await db.businesses.find_one({"business_id": bid}, {"_id": 0})
    if not b: raise HTTPException(404, "Not found")
    owner = await db.users.find_one({"user_id": b["owner_user_id"]}, {"_id": 0, "password_hash": 0})
    files = await db.files.count_documents({"business_id": bid})
    chunks = await db.knowledge_chunks.count_documents({"business_id": bid})
    conv = await db.conversations.count_documents({"business_id": bid})
    msgs = await db.messages.count_documents({"business_id": bid})
    invoices = await db.invoices.find({"business_id": bid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"business": b, "owner": owner, "stats": {"files": files, "kb_chunks": chunks, "conversations": conv, "messages": msgs}, "invoices": invoices}


class BizAction(BaseModel):
    action: str  # suspend | activate | delete | reset_usage | set_plan | extend
    plan: Optional[str] = None
    extra_days: Optional[int] = None
    reason: Optional[str] = None


@router.post("/businesses/{bid}/action")
async def business_action(bid: str, payload: BizAction, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    b = await db.businesses.find_one({"business_id": bid})
    if not b: raise HTTPException(404, "Not found")

    if payload.action == "suspend":
        await db.businesses.update_one({"business_id": bid}, {"$set": {"status": "suspended"}})
    elif payload.action == "activate":
        await db.businesses.update_one({"business_id": bid}, {"$set": {"status": "active"}})
    elif payload.action == "delete":
        await db.businesses.delete_one({"business_id": bid})
        await db.knowledge_chunks.delete_many({"business_id": bid})
        await db.conversations.delete_many({"business_id": bid})
        await db.messages.delete_many({"business_id": bid})
        await db.files.delete_many({"business_id": bid})
    elif payload.action == "reset_usage":
        await db.businesses.update_one({"business_id": bid}, {"$set": {"monthly_used": 0}})
    elif payload.action == "set_plan":
        if payload.plan not in PLANS:
            raise HTTPException(400, "Invalid plan")
        limit = await get_plan_limit(payload.plan, PLANS[payload.plan]["limit"])
        await db.businesses.update_one({"business_id": bid}, {"$set": {"plan": payload.plan, "monthly_limit": limit}})
    elif payload.action == "extend":
        days = payload.extra_days or 30
        await db.businesses.update_one({"business_id": bid}, {"$inc": {"monthly_limit": 500 * (days // 30 or 1)}})
    else:
        raise HTTPException(400, "Unknown action")

    await audit_log(request, user["user_id"], f"business.{payload.action}", "business", bid,
                    {"reason": payload.reason, "plan": payload.plan, "extra_days": payload.extra_days})
    return {"ok": True}


@router.post("/businesses/{bid}/impersonate")
async def impersonate(bid: str, request: Request, response: Response, user=Depends(get_current_user)):
    """Generate a session as the business owner. Records to audit."""
    await _ensure_admin(user)
    b = await db.businesses.find_one({"business_id": bid}, {"_id": 0})
    if not b: raise HTTPException(404, "Not found")
    owner = await db.users.find_one({"user_id": b["owner_user_id"]}, {"_id": 0})
    if not owner: raise HTTPException(404, "Owner not found")
    token = create_token(owner["user_id"], owner["email"])
    await audit_log(request, user["user_id"], "impersonate", "business", bid,
                    {"as_user_id": owner["user_id"], "as_email": owner["email"]})
    return {"token": token, "user": {"user_id": owner["user_id"], "email": owner["email"], "name": owner["name"]}, "impersonation": True, "admin_user_id": user["user_id"]}


# =====================================================================
# USERS
# =====================================================================
@router.get("/users")
async def list_users(q: Optional[str] = None, user=Depends(get_current_user)):
    await _ensure_admin(user)
    query: dict = {}
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"user_id": q},
        ]
    items = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    for u in items:
        u["business_count"] = await db.businesses.count_documents({"owner_user_id": u["user_id"]})
    return items


class UserAction(BaseModel):
    action: str  # disable | enable | make_admin | make_owner | delete


@router.post("/users/{uid}/action")
async def user_action(uid: str, payload: UserAction, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    target = await db.users.find_one({"user_id": uid})
    if not target: raise HTTPException(404, "Not found")

    if payload.action == "disable":
        await db.users.update_one({"user_id": uid}, {"$set": {"disabled": True}})
    elif payload.action == "enable":
        await db.users.update_one({"user_id": uid}, {"$set": {"disabled": False}})
    elif payload.action == "make_admin":
        await db.users.update_one({"user_id": uid}, {"$set": {"role": "admin"}})
    elif payload.action == "make_owner":
        await db.users.update_one({"user_id": uid}, {"$set": {"role": "owner"}})
    elif payload.action == "delete":
        if target["user_id"] == user["user_id"]:
            raise HTTPException(400, "Cannot delete yourself")
        await db.users.delete_one({"user_id": uid})
    else:
        raise HTTPException(400, "Unknown action")

    await audit_log(request, user["user_id"], f"user.{payload.action}", "user", uid, {})
    return {"ok": True}


# =====================================================================
# SUBSCRIPTIONS / INVOICES
# =====================================================================
@router.get("/invoices")
async def all_invoices(format: Optional[str] = None, user=Depends(get_current_user)):
    await _ensure_admin(user)
    items = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for i in items:
        b = await db.businesses.find_one({"business_id": i["business_id"]}, {"_id": 0, "name": 1})
        i["business_name"] = b["name"] if b else None

    if format:
        from exports import export_response
        columns = [
            ("invoice_number", "Invoice #"), ("business_name", "Business"), ("plan", "Plan"),
            ("status", "Status"), ("taxable_value_paise", "Taxable Value (paise)"),
            ("total_tax_paise", "Tax (paise)"), ("total_paise", "Total (paise)"),
            ("is_intra_state", "Intra-state"), ("created_at", "Date"),
        ]
        return export_response(format, items, columns, "invoices", "Invoices Report")
    return items


class RefundIn(BaseModel):
    reason: Optional[str] = None
    amount_paise: Optional[int] = None  # None = full remaining refund


@router.post("/invoices/{invoice_id}/refund")
async def refund_invoice(invoice_id: str, payload: RefundIn, request: Request, user=Depends(get_current_user)):
    """Thin wrapper around the real refund flow (routers/billing.py) -- kept at this URL for
    backward compatibility with existing admin-portal links, but delegates entirely rather
    than duplicating the Razorpay call and GST-aware partial-refund accounting."""
    await _ensure_admin(user)
    from routers.billing import refund as billing_refund, RefundIn as BillingRefundIn
    result = await billing_refund(request, BillingRefundIn(invoice_id=invoice_id, amount_paise=payload.amount_paise,
                                                            reason=payload.reason), user)
    return result


# =====================================================================
# AI USAGE (per business)
# =====================================================================
@router.get("/ai-usage")
async def ai_usage(user=Depends(get_current_user)):
    await _ensure_admin(user)
    out = []
    async for b in db.businesses.find({}, {"_id": 0, "business_id": 1, "name": 1, "plan": 1, "monthly_used": 1, "monthly_limit": 1}):
        msgs = await db.messages.count_documents({"business_id": b["business_id"]})
        est_cost_usd = round(msgs * EST_COST_PER_MSG_USD, 4)
        avg_confidence = 0.0
        # sample: mean confidence of last 200 assistant msgs
        cur = db.messages.find({"business_id": b["business_id"], "role": "assistant", "confidence": {"$exists": True}},
                               {"_id": 0, "confidence": 1}).sort("created_at", -1).limit(200)
        confs = [m["confidence"] async for m in cur]
        if confs:
            avg_confidence = round(sum(confs) / len(confs), 3)
        out.append({
            "business_id": b["business_id"], "name": b["name"], "plan": b.get("plan"),
            "messages": msgs, "est_cost_usd": est_cost_usd,
            "monthly_used": b.get("monthly_used", 0), "monthly_limit": b.get("monthly_limit", 100),
            "avg_confidence": avg_confidence,
        })
    out.sort(key=lambda x: x["messages"], reverse=True)
    return out


# =====================================================================
# CONVERSATIONS EXPLORER
# =====================================================================
@router.get("/conversations")
async def all_conversations(q: Optional[str] = None, unanswered: Optional[bool] = None,
                            escalated: Optional[bool] = None, user=Depends(get_current_user)):
    await _ensure_admin(user)
    query: dict = {}
    if unanswered is not None: query["unanswered"] = unanswered
    if escalated: query["status"] = "escalated"
    items = await db.conversations.find(query, {"_id": 0}).sort("last_message_at", -1).limit(500).to_list(500)
    # attach business name
    for c in items:
        b = await db.businesses.find_one({"business_id": c["business_id"]}, {"_id": 0, "name": 1})
        c["business_name"] = b["name"] if b else None
    if q:
        # keyword search on messages
        matching_conv_ids = set()
        async for m in db.messages.find({"text": {"$regex": q, "$options": "i"}}, {"_id": 0, "conversation_id": 1}).limit(500):
            matching_conv_ids.add(m["conversation_id"])
        items = [c for c in items if c["conversation_id"] in matching_conv_ids]
    return items


# =====================================================================
# KNOWLEDGE MANAGER
# =====================================================================
@router.get("/knowledge")
async def all_knowledge(user=Depends(get_current_user)):
    await _ensure_admin(user)
    files = await db.files.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    for f in files:
        b = await db.businesses.find_one({"business_id": f["business_id"]}, {"_id": 0, "name": 1})
        f["business_name"] = b["name"] if b else None
    return files


@router.get("/crawls")
async def all_crawls(user=Depends(get_current_user)):
    await _ensure_admin(user)
    items = await db.businesses.find({"website": {"$exists": True, "$nin": [None, ""]}},
                                     {"_id": 0, "business_id": 1, "name": 1, "website": 1, "crawl_status": 1, "crawl_progress": 1, "knowledge_score": 1}).to_list(500)
    for b in items:
        b["chunks"] = await db.knowledge_chunks.count_documents({"business_id": b["business_id"]})
    return items


@router.post("/businesses/{bid}/recrawl")
async def admin_recrawl(bid: str, bg: BackgroundTasks, request: Request, user=Depends(get_current_user)):
    """Same action as the owner-facing POST /businesses/{id}/recrawl, but not scoped to
    owner_user_id -- an admin re-triggering a crawl from the Crawlers page is never the
    business's owner, so that endpoint always 404s for admins. Kept separate rather than
    loosening the owner route's ownership check."""
    await _ensure_admin(user)
    from routers.businesses import _run_crawl
    biz = await db.businesses.find_one({"business_id": bid}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    if not biz.get("website"):
        raise HTTPException(400, "No website set")
    await db.knowledge_chunks.delete_many({"business_id": bid, "source": {"$regex": "^http"}})
    invalidate(bid)
    bg.add_task(_run_crawl, bid, biz["website"])
    await db.businesses.update_one({"business_id": bid}, {"$set": {"crawl_status": "crawling", "crawl_progress": 5}})
    await audit_log(request, user["user_id"], "admin.business.recrawl", "business", bid, {})
    return {"ok": True}


# =====================================================================
# REFERRALS
# =====================================================================
@router.get("/referrals")
async def all_referrals(user=Depends(get_current_user)):
    await _ensure_admin(user)
    refs = await db.referrals.find({}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    for r in refs:
        owner = await db.users.find_one({"referral_code": r["code"]}, {"_id": 0, "email": 1, "name": 1})
        referred = await db.users.find_one({"user_id": r["referred_user_id"]}, {"_id": 0, "email": 1, "name": 1})
        r["referrer_email"] = owner.get("email") if owner else None
        r["referred_email"] = referred.get("email") if referred else None
    return refs


@router.get("/enterprise-leads")
async def list_enterprise_leads(user=Depends(get_current_user)):
    """Backstop for POST /billing/enterprise-inquiry -- every lead lands here regardless of
    whether the notification email was configured/delivered, so nothing gets lost to an
    inbox nobody checked."""
    await _ensure_admin(user)
    return await db.enterprise_leads.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)


# =====================================================================
# COUPONS
# =====================================================================
class Coupon(BaseModel):
    code: str
    discount_pct: int = Field(ge=1, le=100)
    max_redemptions: int = 100
    expires_at: Optional[str] = None
    active: bool = True


@router.get("/coupons")
async def list_coupons(user=Depends(get_current_user)):
    await _ensure_admin(user)
    return await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/coupons")
async def create_coupon(payload: Coupon, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    doc = payload.model_dump()
    doc["code"] = doc["code"].upper()
    if await db.coupons.find_one({"code": doc["code"]}):
        raise HTTPException(400, "Coupon code exists")
    doc["id"] = str(uuid.uuid4())
    doc["redemptions"] = 0
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.coupons.insert_one(doc)
    await audit_log(request, user["user_id"], "coupon.create", "coupon", doc["code"], {"discount_pct": doc["discount_pct"]})
    doc.pop("_id", None)
    return doc


@router.delete("/coupons/{code}")
async def delete_coupon(code: str, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    res = await db.coupons.delete_one({"code": code.upper()})
    if res.deleted_count == 0: raise HTTPException(404, "Not found")
    await audit_log(request, user["user_id"], "coupon.delete", "coupon", code, {})
    return {"ok": True}


# =====================================================================
# SUPPORT TICKETS (from notifications type=handoff)
# =====================================================================
@router.get("/tickets")
async def list_tickets(status: Optional[str] = None, user=Depends(get_current_user)):
    await _ensure_admin(user)
    query: dict = {"type": "handoff"}
    if status == "open": query["read"] = False
    if status == "closed": query["read"] = True
    items = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    for t in items:
        b = await db.businesses.find_one({"business_id": t["business_id"]}, {"_id": 0, "name": 1})
        t["business_name"] = b["name"] if b else None
    return items


class TicketAction(BaseModel):
    status: str  # closed | open
    note: Optional[str] = None


@router.post("/tickets/{ticket_id}/action")
async def ticket_action(ticket_id: str, payload: TicketAction, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    read = payload.status == "closed"
    await db.notifications.update_one({"id": ticket_id}, {"$set": {"read": read, "admin_note": payload.note}})
    await audit_log(request, user["user_id"], f"ticket.{payload.status}", "ticket", ticket_id, {"note": payload.note})
    return {"ok": True}


# =====================================================================
# BROADCAST NOTIFICATIONS
# =====================================================================
class Broadcast(BaseModel):
    title: str
    message: str
    audience: str = "all"  # all | free | paid | specific
    business_ids: Optional[List[str]] = None
    severity: str = "info"  # info | warning | urgent


@router.get("/broadcasts")
async def list_broadcasts(user=Depends(get_current_user)):
    await _ensure_admin(user)
    return await db.broadcasts.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/broadcasts")
async def create_broadcast(payload: Broadcast, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["user_id"]

    # figure recipients
    biz_q: dict = {}
    if payload.audience == "free": biz_q["plan"] = "free"
    elif payload.audience == "paid": biz_q["plan"] = {"$ne": "free"}
    elif payload.audience == "specific" and payload.business_ids:
        biz_q["business_id"] = {"$in": payload.business_ids}
    recipients = await db.businesses.find(biz_q, {"_id": 0, "business_id": 1}).to_list(5000)
    doc["recipient_count"] = len(recipients)
    await db.broadcasts.insert_one(doc)

    # write to each business's notifications
    for r in recipients:
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "business_id": r["business_id"],
            "type": "announcement",
            "title": payload.title,
            "message": payload.message,
            "severity": payload.severity,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    await audit_log(request, user["user_id"], "broadcast.create", "broadcast", doc["id"], {"audience": payload.audience, "recipients": len(recipients)})
    doc.pop("_id", None)
    return doc


# =====================================================================
# FEATURE FLAGS
# =====================================================================
DEFAULT_FLAGS = {
    "referrals_enabled": True,
    "widget_customization": True,
    "file_uploads": True,
    "website_crawler": True,
    "owner_write_actions": True,
    "human_handoff": True,
}


@router.get("/flags")
async def get_flags(user=Depends(get_current_user)):
    await _ensure_admin(user)
    out = {}
    for k, v in DEFAULT_FLAGS.items():
        doc = await db.feature_flags.find_one({"key": k}, {"_id": 0})
        out[k] = doc["value"] if doc else v
    return out


class FlagUpdate(BaseModel):
    key: str
    value: bool


@router.post("/flags")
async def set_flag(payload: FlagUpdate, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    if payload.key not in DEFAULT_FLAGS:
        raise HTTPException(400, "Unknown flag")
    await db.feature_flags.update_one({"key": payload.key},
                                      {"$set": {"key": payload.key, "value": payload.value,
                                                "updated_at": datetime.now(timezone.utc).isoformat()}},
                                      upsert=True)
    await audit_log(request, user["user_id"], "flag.set", "flag", payload.key, {"value": payload.value})
    return {"ok": True}


# =====================================================================
# SYSTEM MONITORING
# =====================================================================
@router.get("/system")
async def system(user=Depends(get_current_user)):
    await _ensure_admin(user)
    try:
        import psutil, platform, os as _os
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        info = {
            "cpu_pct": cpu,
            "mem_pct": mem.percent,
            "mem_used_gb": round(mem.used / 1024**3, 2),
            "mem_total_gb": round(mem.total / 1024**3, 2),
            "disk_pct": disk.percent,
            "disk_used_gb": round(disk.used / 1024**3, 2),
            "disk_total_gb": round(disk.total / 1024**3, 2),
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
    except Exception:
        info = {"cpu_pct": 0, "mem_pct": 0, "note": "psutil not available"}

    try:
        ping = await db.command("ping")
        db_ok = ping.get("ok") == 1
    except Exception:
        db_ok = False

    return {
        "system": info,
        "services": {
            "mongodb": "healthy" if db_ok else "down",
            "backend": "healthy",
            "gemini": "configured" if config.GEMINI_API_KEY else "not_configured",
            "storage": "s3" if config.USE_S3_STORAGE else "local_disk",
            "payments": "configured" if config.RAZORPAY_ENABLED else "not_configured",
        },
        "version": "1.0.0",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# =====================================================================
# AUDIT LOG
# =====================================================================
@router.get("/audit")
async def audit(q: Optional[str] = None, user=Depends(get_current_user)):
    await _ensure_admin(user)
    query: dict = {}
    if q:
        query["$or"] = [
            {"action": {"$regex": q, "$options": "i"}},
            {"target_id": {"$regex": q, "$options": "i"}},
            {"actor_user_id": q},
        ]
    items = await db.audit_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    for i in items:
        actor = await db.users.find_one({"user_id": i.get("actor_user_id")}, {"_id": 0, "email": 1})
        i["actor_email"] = actor.get("email") if actor else None
    return items


# =====================================================================
# SETTINGS
# =====================================================================
from platform_settings import DEFAULTS as DEFAULT_SETTINGS, get_settings as _get_platform_settings


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    await _ensure_admin(user)
    return await _get_platform_settings()


@router.put("/settings")
async def update_settings(payload: dict, request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    # only allow whitelisted keys
    filtered = {k: v for k, v in payload.items() if k in DEFAULT_SETTINGS}
    await db.platform_settings.update_one({"_id": "singleton"}, {"$set": filtered}, upsert=True)
    await audit_log(request, user["user_id"], "settings.update", "settings", "singleton", {"changed": list(filtered.keys())})
    return {"ok": True}


# =====================================================================
# CRON -- lets an admin trigger the weekly re-crawl + staleness-nudge jobs on
# demand (useful for testing), and gives an external cron a stable endpoint
# to hit if you've disabled the in-process scheduler (ENABLE_SCHEDULER=false)
# for a multi-instance deployment. Slower than a typical request -- re-crawls
# every business sequentially -- so call it from a background-tolerant cron,
# not something waiting on a fast response.
# =====================================================================
@router.post("/cron/run-weekly-jobs")
async def trigger_weekly_jobs(request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    from scheduler import run_weekly_jobs
    result = await run_weekly_jobs()
    await audit_log(request, user["user_id"], "cron.run_weekly_jobs", "system", "weekly_jobs", result)
    return {"ok": True, **result}


@router.post("/cron/run-billing-lifecycle")
async def trigger_billing_lifecycle(request: Request, user=Depends(get_current_user)):
    await _ensure_admin(user)
    from scheduler import billing_lifecycle_job
    result = await billing_lifecycle_job()
    await audit_log(request, user["user_id"], "cron.run_billing_lifecycle", "system", "billing_lifecycle", result)
    return {"ok": True, **result}


@router.post("/cron/run-plan-snapshot")
async def trigger_plan_snapshot(request: Request, user=Depends(get_current_user)):
    """Manually seeds/refreshes this month's paying-business snapshot -- run this once
    right after deploying so /admin/churn has real data for the current month instead of
    waiting for the 1st of next month."""
    await _ensure_admin(user)
    from scheduler import plan_snapshot_job
    result = await plan_snapshot_job()
    await audit_log(request, user["user_id"], "cron.run_plan_snapshot", "system", "plan_snapshot", result)
    return {"ok": True, **result}
@router.post('/sales/onboard')
async def onboard_sales_agent(data: dict, current_user=Depends(get_current_admin_user)):
    """
    Creates a sales user, generates a temp password, sends email via Resend,
    and returns the credentials to the admin.
    """
    name = data.get('name')
    email = data.get('email')
    company = data.get('company')
    
    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email required")

    # 1. Generate Temp Password
    temp_password = secrets.token_urlsafe(12)
    hashed_pw = get_password_hash(temp_password)

    # 2. Create User in DB with role 'sales'
    try:
        new_user = db.execute(
            "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (%s, %s, %s, 'sales', NOW()) RETURNING id",
            (name, email, hashed_pw)
        ).fetchone()
        
        # 3. Link to Sales Profile (if you have a separate sales_profiles table)
        # db.execute("INSERT INTO sales_profiles ...") 
        
    except Exception as e:
        if "unique_email" in str(e):
            raise HTTPException(status_code=400, detail="Email already registered")
        raise e

    # 4. Send Email via Resend (using your existing email service)
    login_url = f"{FRONTEND_URL}/login" # Or specific sales portal URL
    
    await send_email(
        to=email,
        subject="Welcome to Roviq Sales Team - Action Required",
        html=f"""
        <h1>Welcome {name}!</h1>
        <p>You have been onboarded as a Sales Agent for {company}.</p>
        <p><strong>Login URL:</strong> <a href="{login_url}">{login_url}</a></p>
        <p><strong>Temporary Password:</strong> <code>{temp_password}</code></p>
        <p>Please log in and change your password immediately.</p>
        <p>You will earn a 15% commission on every paid plan purchased by businesses you onboard.</p>
        """
    )

    return {
        "message": "User created and email sent",
        "email": email,
        "tempPassword": temp_password,
        "loginUrl": login_url
    }
