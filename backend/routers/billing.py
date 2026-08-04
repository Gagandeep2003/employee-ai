"""Billing: Razorpay checkout (domestic/INR), GST-compliant invoicing, proration, grace
periods/dunning, and refunds.

Deliberately built on one-off Razorpay Orders, not Razorpay's separate Subscriptions
product -- keeps the integration simple (one webhook surface, no recurring-mandate UX) at
the cost of no auto-recurring charge. subscriptions.py and scheduler.py's
billing_lifecycle_job cover that gap: a renewal reminder before the period ends, a grace
period of continued access if it lapses, and only then an auto-downgrade to free.

Plan prices (PLANS below) are GST-inclusive -- "Rs 999/month, inclusive of GST" -- so the
amount actually charged at checkout is unchanged from before GST invoicing existed; the
invoice back-calculates the CGST/SGST/IGST split from that charged total (see gst.py).

International payments are intentionally out of scope for now (Razorpay Checkout defaults
to Indian payment methods -- UPI, cards, netbanking, wallets -- when currency is INR, so no
extra config is needed to keep this domestic-only).
"""
import hmac
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import config
from auth import get_current_user
from db import db
from platform_settings import get_plan_limit, get_settings
from audit import log as audit_log
from ratelimit import limiter
import gst
import invoicing
import subscriptions
import usage
from storage import get_object
from email_sender import (
    send_refund_processed_email, send_upgrade_confirmed_email,
    send_subscription_change_scheduled_email, send_cancellation_confirmed_email,
    send_referral_reward_email,
)

logger = logging.getLogger("roviq-ai.billing")
router = APIRouter(prefix="/billing", tags=["billing"])

# Prices are GST-inclusive, in rupees, alongside paise for Razorpay. Margins at these price
# points are comfortable even accounting for Gemini 3.1 Flash-Lite API costs (~$0.0005-0.0008
# per chat turn incl. RAG context) -- see DEPLOYMENT.md for the full cost breakdown.
PLANS = {
    "free": {"name": "Free", "price_inr": 0, "limit": 100,
             "features": ["100 chats / month", "Roviq Ai watermark", "1 business"]},
    "starter": {"name": "Starter", "price_inr": 999, "limit": 2000,
                "features": ["2,000 chats / month", "No branding", "Widget customization", "Email support"]},
    "growth": {"name": "Growth", "price_inr": 2999, "limit": 10000,
               "features": ["10,000 chats / month", "Advanced analytics", "Priority support", "Unlimited knowledge uploads"]},
    "scale": {"name": "Scale", "price_inr": 4999, "limit": 25000,
              "features": ["25,000 chats / month", "Everything in Growth", "Higher-volume priority support"]},
    # Legacy -- "pro" was renamed to "growth" (identical price/limit/features) to match the
    # product's actual tier naming. Kept here, not deleted, so a business record that already
    # has plan="pro" keeps resolving correctly everywhere PLANS[biz["plan"]] is looked up --
    # "hidden" excludes it from /plans so new signups and the pricing page only ever offer
    # "growth". Safe to delete once/if you've confirmed no business is still on "pro".
    "pro": {"name": "Pro", "price_inr": 2999, "limit": 10000,
            "features": ["10,000 chats / month", "Advanced analytics", "Priority support", "Unlimited knowledge uploads"],
            "hidden": True},
}


def _razorpay_client():
    if not config.RAZORPAY_ENABLED:
        raise HTTPException(503, "Payments are not configured on this deployment yet. Please contact support.")
    import razorpay
    client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    client.set_app_details({"title": "Roviq-Ai", "version": "1.0"})
    return client


async def _verify_ownership(business_id: str, user: dict) -> dict:
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz


@router.get("/plans")
async def get_plans():
    out = {}
    for key, info in PLANS.items():
        if info.get("hidden"):
            continue
        limit = await get_plan_limit(key, info["limit"])
        out[key] = {**info, "limit": limit, "gst_inclusive": True}
    return out


# ---------------------------------------------------------------------------
# Enterprise -- deliberately not a fixed self-serve price. "Custom pricing" means a real
# conversation (volume, SLAs, contract terms), not a checkout button, so this is a lead
# capture + notification instead of a PLANS entry.
# ---------------------------------------------------------------------------
class EnterpriseInquiry(BaseModel):
    name: str
    email: str
    business_name: str
    message: Optional[str] = None
    business_id: Optional[str] = None  # set when submitted from inside the app, so it can be linked


@router.post("/enterprise-inquiry")
@limiter.limit("5/hour")
async def enterprise_inquiry(request: Request, payload: EnterpriseInquiry):
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": lead_id, "name": payload.name.strip(), "email": payload.email.strip(),
        "business_name": payload.business_name.strip(), "message": (payload.message or "").strip(),
        "business_id": payload.business_id, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.enterprise_leads.insert_one(dict(doc))

    settings = await get_settings()
    support_email = settings.get("support_email")
    if support_email:
        body = (
            f"New Enterprise plan inquiry:\n\n"
            f"Name: {doc['name']}\nEmail: {doc['email']}\nBusiness: {doc['business_name']}\n"
            f"Message: {doc['message'] or '(none)'}\n"
        )
        try:
            from email_sender import send_email
            await send_email(support_email, f"Enterprise inquiry: {doc['business_name']}", body, reply_to=doc["email"])
        except Exception as e:
            logger.warning("Enterprise inquiry email failed (lead still saved): %s", e)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Subscribe / plan changes
# ---------------------------------------------------------------------------
class Subscribe(BaseModel):
    business_id: str
    plan: str


@router.post("/subscribe")
async def subscribe(payload: Subscribe, user=Depends(get_current_user)):
    """Creates a Razorpay order for a paid plan (or switches instantly for the free plan).
    A switch between two paid plans is prorated: an upgrade (or same-price switch) goes to
    checkout immediately for just the prorated difference; a downgrade is scheduled to take
    effect at the end of the current paid period instead of losing paid access early. The
    plan is only applied after /billing/verify confirms the payment signature, or the
    /billing/webhook receives a payment.captured event."""
    if payload.plan not in PLANS:
        raise HTTPException(400, "Invalid plan")
    biz = await _verify_ownership(payload.business_id, user)
    plan_info = PLANS[payload.plan]
    old_plan = biz.get("plan", "free")

    if payload.plan == "free":
        if old_plan != "free":
            await subscriptions.cancel_subscription(payload.business_id, immediate=True)
        else:
            limit = await get_plan_limit("free", plan_info["limit"])
            await db.businesses.update_one({"business_id": payload.business_id}, {"$set": {"monthly_limit": limit}})
        return {"ok": True, "plan": "free", "requires_payment": False}

    new_price_paise = plan_info["price_inr"] * 100
    old_price_paise = PLANS.get(old_plan, {}).get("price_inr", 0) * 100

    if old_plan != "free" and new_price_paise < old_price_paise and biz.get("current_period_end"):
        await subscriptions.schedule_downgrade(payload.business_id, payload.plan)
        try:
            await send_subscription_change_scheduled_email(
                user["email"], user.get("name"), biz["name"], plan_info["name"],
                biz["current_period_end"][:10],
            )
        except Exception as e:
            logger.warning("Subscription-change email failed: %s", e)
        return {"ok": True, "plan": old_plan, "requires_payment": False,
                "scheduled_plan_change": payload.plan, "effective_at": biz.get("current_period_end")}

    client = _razorpay_client()
    proration_paise = subscriptions.compute_proration(old_plan, payload.plan, biz.get("current_period_end"), PLANS)
    due_paise = await usage.outstanding_due_paise(payload.business_id)
    # First paid purchase (old_plan == free): full price. Upgrade/same-price switch from an
    # existing paid plan: just the prorated top-up -- apply_immediate_plan_change resets the
    # period to a fresh 30 days on the new plan, so charging the full new price on top of
    # the proration would double-charge for the days already paid for on the old plan.
    amount_paise = new_price_paise if old_plan == "free" else max(proration_paise, 0)
    amount_paise += due_paise

    if amount_paise == 0:
        # A prior downgrade-then-upgrade credit fully covers this switch -- apply immediately.
        limit = await get_plan_limit(payload.plan, plan_info["limit"])
        await subscriptions.apply_immediate_plan_change(payload.business_id, payload.plan, limit)
        return {"ok": True, "plan": payload.plan, "requires_payment": False}

    order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"{payload.business_id}_{payload.plan}_{uuid.uuid4().hex[:8]}",
        "notes": {"business_id": payload.business_id, "plan": payload.plan, "user_id": user["user_id"]},
    })

    await db.payment_orders.insert_one({
        "id": str(uuid.uuid4()),
        "razorpay_order_id": order["id"],
        "business_id": payload.business_id,
        "user_id": user["user_id"],
        "plan": payload.plan,
        "amount_inr": round(amount_paise / 100),
        "amount_paise": amount_paise,
        "plan_amount_paise": amount_paise - due_paise,  # excludes any folded-in due overage -- see _activate_plan_for_order
        "is_proration": proration_paise != 0,
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "ok": True, "requires_payment": True, "order_id": order["id"], "amount": amount_paise,
        "currency": "INR", "key_id": config.RAZORPAY_KEY_ID, "business_name": biz.get("name"),
        "proration_applied": proration_paise != 0,
    }


class CancelIn(BaseModel):
    business_id: str
    immediate: bool = False


@router.post("/cancel")
async def cancel(payload: CancelIn, user=Depends(get_current_user)):
    """immediate=false (default): the business keeps paid access until the current period
    ends, then drops to free -- no partial refund for time already paid for. immediate=true:
    drops to free right away."""
    biz = await _verify_ownership(payload.business_id, user)
    await subscriptions.cancel_subscription(payload.business_id, immediate=payload.immediate)
    try:
        await send_cancellation_confirmed_email(
            user["email"], user.get("name"), biz["name"], payload.immediate,
            access_until=(biz.get("current_period_end") or "")[:10] if not payload.immediate else None,
        )
    except Exception as e:
        logger.warning("Cancellation email failed: %s", e)
    return {"ok": True, "immediate": payload.immediate}


# ---------------------------------------------------------------------------
# Payment verification / webhook / invoice activation
# ---------------------------------------------------------------------------
class VerifyPayment(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


async def _activate_plan_for_order(order_doc: dict):
    """Idempotent: safe to call from both /verify and the webhook."""
    if order_doc.get("status") == "paid":
        return
    plan_info = PLANS[order_doc["plan"]]
    limit = await get_plan_limit(order_doc["plan"], plan_info["limit"])
    await subscriptions.apply_immediate_plan_change(order_doc["business_id"], order_doc["plan"], limit)
    await db.payment_orders.update_one({"razorpay_order_id": order_doc["razorpay_order_id"]},
                                       {"$set": {"status": "paid"}})

    amount_paise = order_doc.get("plan_amount_paise", order_doc.get("amount_paise", plan_info["price_inr"] * 100))
    description = (f"{plan_info['name']} plan -- prorated adjustment" if order_doc.get("is_proration")
                   else f"{plan_info['name']} plan subscription")
    invoice = None
    if amount_paise != 0:
        invoice = await invoicing.create_invoice(
            order_doc["business_id"], order_doc["user_id"], order_doc["plan"], amount_paise,
            description=description, razorpay_order_id=order_doc["razorpay_order_id"],
            razorpay_payment_id=order_doc.get("razorpay_payment_id"),
        )
    if order_doc.get("razorpay_payment_id"):
        await usage.mark_due_invoices_paid(order_doc["business_id"], order_doc["razorpay_payment_id"])

    # reward referrer on the referred user's first paid plan (not on every subsequent purchase)
    user = await db.users.find_one({"user_id": order_doc["user_id"]})
    biz = await db.businesses.find_one({"business_id": order_doc["business_id"]}, {"_id": 0, "name": 1})
    if user and user.get("referred_by_code"):
        result = await db.referrals.update_one(
            {"code": user["referred_by_code"], "referred_user_id": user["user_id"], "status": {"$ne": "rewarded"}},
            {"$set": {"status": "rewarded", "rewarded_at": datetime.now(timezone.utc).isoformat()}}
        )
        if result.modified_count:
            referrer = await db.users.find_one({"referral_code": user["referred_by_code"]}, {"_id": 0})
            if referrer:
                try:
                    await send_referral_reward_email(referrer["email"], referrer.get("name"), (biz or {}).get("name", "a referred business"))
                except Exception as e:
                    logger.warning("Referral reward email failed: %s", e)

    if not order_doc.get("is_proration"):
        try:
            if user and biz:
                await send_upgrade_confirmed_email(user["email"], user.get("name"), biz["name"], plan_info["name"])
        except Exception as e:
            logger.warning("Upgrade confirmation email failed: %s", e)

    return invoice


@router.post("/verify")
async def verify_payment(payload: VerifyPayment, user=Depends(get_current_user)):
    client = _razorpay_client()
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
    except Exception:
        raise HTTPException(400, "Payment signature verification failed")

    order_doc = await db.payment_orders.find_one({"razorpay_order_id": payload.razorpay_order_id})
    if not order_doc or order_doc["user_id"] != user["user_id"]:
        raise HTTPException(404, "Order not found")

    await db.payment_orders.update_one({"razorpay_order_id": payload.razorpay_order_id},
                                       {"$set": {"razorpay_payment_id": payload.razorpay_payment_id}})
    order_doc["razorpay_payment_id"] = payload.razorpay_payment_id
    await _activate_plan_for_order(order_doc)
    return {"ok": True, "plan": order_doc["plan"]}


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """Safety net for payment.captured / payment.failed / refund.processed events --
    handles cases where the browser closes before /verify is called. Register this
    URL (<your-domain>/api/billing/webhook) in the Razorpay dashboard."""
    if not config.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook not configured")

    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid webhook signature")

    import json
    event = json.loads(body)
    event_type = event.get("event")

    if event_type == "payment.captured":
        order_id = event["payload"]["payment"]["entity"]["order_id"]
        payment_id = event["payload"]["payment"]["entity"]["id"]
        order_doc = await db.payment_orders.find_one({"razorpay_order_id": order_id})
        if order_doc:
            order_doc["razorpay_payment_id"] = payment_id
            await _activate_plan_for_order(order_doc)

    elif event_type == "payment.failed":
        order_id = event["payload"]["payment"]["entity"]["order_id"]
        await db.payment_orders.update_one({"razorpay_order_id": order_id}, {"$set": {"status": "failed"}})

    elif event_type == "refund.processed":
        payment_id = event["payload"]["refund"]["entity"]["payment_id"]
        refund_amount = event["payload"]["refund"]["entity"].get("amount", 0)
        inv = await db.invoices.find_one({"razorpay_payment_id": payment_id})
        if inv:
            await _apply_refund(inv, refund_amount, source="webhook")
    else:
        logger.info("Unhandled Razorpay webhook event: %s", event_type)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
@router.get("/invoices/{business_id}")
async def invoices(business_id: str, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    items = await db.invoices.find({"business_id": business_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return items


@router.get("/invoices/{business_id}/{invoice_id}/pdf")
async def invoice_pdf(business_id: str, invoice_id: str, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    inv = await db.invoices.find_one({"id": invoice_id, "business_id": business_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")

    if inv.get("pdf_path"):
        try:
            data, _ = get_object(inv["pdf_path"])
            return Response(content=data, media_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}.pdf"'})
        except FileNotFoundError:
            pass  # fall through to regenerate on the fly

    from invoice_pdf import render_invoice_pdf
    data = render_invoice_pdf(inv)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}.pdf"'})


# ---------------------------------------------------------------------------
# GST details (owner-managed)
# ---------------------------------------------------------------------------
class GstDetailsIn(BaseModel):
    gst_state_code: Optional[str] = None
    gstin: Optional[str] = None
    billing_legal_name: Optional[str] = None
    billing_address: Optional[str] = None


@router.get("/gst-details/{business_id}")
async def get_gst_details(business_id: str, user=Depends(get_current_user)):
    biz = await _verify_ownership(business_id, user)
    return {
        "gst_state_code": biz.get("gst_state_code"),
        "gstin": biz.get("gstin"),
        "billing_legal_name": biz.get("billing_legal_name"),
        "billing_address": biz.get("billing_address"),
        "state_options": gst.INDIA_STATE_CODES,
    }


@router.put("/gst-details/{business_id}")
async def set_gst_details(business_id: str, payload: GstDetailsIn, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    if payload.gst_state_code and payload.gst_state_code not in gst.INDIA_STATE_CODES:
        raise HTTPException(400, "Invalid state code")
    if payload.gstin and not gst.validate_gstin(payload.gstin):
        raise HTTPException(400, "That doesn't look like a valid 15-character GSTIN")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await db.businesses.update_one({"business_id": business_id}, {"$set": updates})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Refunds -- admin-initiated (same trust model as any payment processor's dashboard:
# refund issuance goes through support/admin, not customer self-service, to prevent abuse).
# ---------------------------------------------------------------------------
class RefundIn(BaseModel):
    invoice_id: str
    amount_paise: Optional[int] = None  # None = full remaining refund
    reason: Optional[str] = None


async def _apply_refund(inv: dict, refund_amount_paise: int, source: str):
    already_refunded = inv.get("refund_amount_paise", 0)
    new_total_refunded = already_refunded + refund_amount_paise
    status = "refunded" if new_total_refunded >= inv.get("total_paise", 0) else "partially_refunded"
    await db.invoices.update_one({"id": inv["id"]}, {"$set": {
        "refund_amount_paise": new_total_refunded, "refunded_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }})
    if status == "refunded":
        free_limit = await get_plan_limit("free", PLANS["free"]["limit"])
        await subscriptions.cancel_subscription(inv["business_id"], immediate=True)
        await db.businesses.update_one({"business_id": inv["business_id"]}, {"$set": {"monthly_limit": free_limit}})

    user = await db.users.find_one({"user_id": inv["user_id"]}, {"_id": 0})
    biz = await db.businesses.find_one({"business_id": inv["business_id"]}, {"_id": 0})
    if user and biz:
        try:
            await send_refund_processed_email(user["email"], user.get("name"), biz["name"],
                                              f"Rs. {refund_amount_paise / 100:,.2f}")
        except Exception as e:
            logger.warning("Refund email failed: %s", e)
    logger.info("Refund applied to invoice %s via %s: %d paise (total now %d)",
                inv["id"], source, refund_amount_paise, new_total_refunded)


@router.post("/refund")
async def refund(request: Request, payload: RefundIn, user=Depends(get_current_user)):
    from routers.admin import _ensure_admin
    await _ensure_admin(user)

    inv = await db.invoices.find_one({"id": payload.invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if not inv.get("razorpay_payment_id"):
        raise HTTPException(400, "This invoice has no associated payment to refund")

    remaining = inv.get("total_paise", 0) - inv.get("refund_amount_paise", 0)
    amount = payload.amount_paise if payload.amount_paise is not None else remaining
    if amount <= 0 or amount > remaining:
        raise HTTPException(400, f"Refund amount must be between 1 and {remaining} paise")

    client = _razorpay_client()
    try:
        client.payment.refund(inv["razorpay_payment_id"], {"amount": amount, "notes": {"reason": payload.reason or ""}})
    except Exception as e:
        raise HTTPException(502, f"Razorpay refund failed: {e}")

    await _apply_refund(inv, amount, source="admin")
    await audit_log(request, user["user_id"], "billing.refund_issued", "invoice", payload.invoice_id,
                    {"amount_paise": amount, "reason": payload.reason})
    return {"ok": True, "refunded_paise": amount}
