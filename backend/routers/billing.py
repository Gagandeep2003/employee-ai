"""Billing: Razorpay checkout (domestic/INR) with real order creation, signature
verification, and webhook handling. Free plan requires no payment step.

International payments are intentionally out of scope for now (Razorpay Checkout
defaults to Indian payment methods -- UPI, cards, netbanking, wallets -- when
currency is INR, so no extra config is needed to keep this domestic-only).
"""
import hmac
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import config
from auth import get_current_user
from db import db
from usage import current_period
from platform_settings import get_plan_limit

logger = logging.getLogger("ai-employee.billing")
router = APIRouter(prefix="/billing", tags=["billing"])

# Prices are in paise (INR's smallest unit) alongside a human-readable rupee value.
# Margins at these price points are comfortable even accounting for Gemini 3.1
# Flash-Lite API costs (~$0.0005-0.0008 per chat turn incl. RAG context) -- see
# DEPLOYMENT.md for the full cost breakdown.
PLANS = {
    "free": {"name": "Free", "price_inr": 0, "limit": 100,
             "features": ["100 chats / month", "AI Employee watermark", "1 business"]},
    "starter": {"name": "Starter", "price_inr": 999, "limit": 2000,
                "features": ["2,000 chats / month", "No branding", "Widget customization", "Email support"]},
    "pro": {"name": "Pro", "price_inr": 2999, "limit": 10000,
            "features": ["10,000 chats / month", "Advanced analytics", "Priority support", "Unlimited knowledge uploads"]},
}


def _razorpay_client():
    if not config.RAZORPAY_ENABLED:
        raise HTTPException(503, "Payments are not configured on this deployment yet. Please contact support.")
    import razorpay
    client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    client.set_app_details({"title": "AI-Employee", "version": "1.0"})
    return client


@router.get("/plans")
async def get_plans():
    out = {}
    for key, info in PLANS.items():
        limit = await get_plan_limit(key, info["limit"])
        out[key] = {**info, "limit": limit}
    return out


class Subscribe(BaseModel):
    business_id: str
    plan: str


@router.post("/subscribe")
async def subscribe(payload: Subscribe, user=Depends(get_current_user)):
    """Creates a Razorpay order for a paid plan (or switches instantly for the free plan).
    The plan is only applied to the business after /billing/verify confirms the
    payment signature, or the /billing/webhook receives a payment.captured event."""
    if payload.plan not in PLANS:
        raise HTTPException(400, "Invalid plan")
    biz = await db.businesses.find_one({"business_id": payload.business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")

    plan_info = PLANS[payload.plan]

    if payload.plan == "free":
        limit = await get_plan_limit("free", plan_info["limit"])
        await db.businesses.update_one(
            {"business_id": payload.business_id},
            {"$set": {"plan": "free", "monthly_limit": limit}}
        )
        return {"ok": True, "plan": "free", "requires_payment": False}

    client = _razorpay_client()
    amount_paise = plan_info["price_inr"] * 100
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
        "amount_inr": plan_info["price_inr"],
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "ok": True,
        "requires_payment": True,
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key_id": config.RAZORPAY_KEY_ID,
        "business_name": biz.get("name"),
    }


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
    await db.businesses.update_one(
        {"business_id": order_doc["business_id"]},
        {"$set": {"plan": order_doc["plan"], "monthly_limit": limit}}
    )
    await db.payment_orders.update_one({"razorpay_order_id": order_doc["razorpay_order_id"]},
                                       {"$set": {"status": "paid"}})
    invoice = {
        "id": f"inv_{uuid.uuid4().hex[:10]}",
        "business_id": order_doc["business_id"],
        "user_id": order_doc["user_id"],
        "plan": order_doc["plan"],
        "amount_inr": plan_info["price_inr"],
        "status": "paid",
        "provider": "razorpay",
        "razorpay_order_id": order_doc["razorpay_order_id"],
        "razorpay_payment_id": order_doc.get("razorpay_payment_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.invoices.insert_one(invoice)

    # reward referrer if this is the user's first paid plan
    user = await db.users.find_one({"user_id": order_doc["user_id"]})
    if user and user.get("referred_by_code"):
        await db.referrals.update_one(
            {"code": user["referred_by_code"], "referred_user_id": user["user_id"]},
            {"$set": {"status": "rewarded", "rewarded_at": datetime.now(timezone.utc).isoformat()}}
        )


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
        inv = await db.invoices.find_one({"razorpay_payment_id": payment_id})
        if inv:
            await db.invoices.update_one({"id": inv["id"]}, {"$set": {"status": "refunded"}})
            free_limit = await get_plan_limit("free", PLANS["free"]["limit"])
            await db.businesses.update_one({"business_id": inv["business_id"]},
                                           {"$set": {"plan": "free", "monthly_limit": free_limit}})
    else:
        logger.info("Unhandled Razorpay webhook event: %s", event_type)

    return {"status": "ok"}


@router.get("/invoices/{business_id}")
async def invoices(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    items = await db.invoices.find({"business_id": business_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return items
