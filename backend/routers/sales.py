"""Sales team portal for onboarding businesses and tracking commissions."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import secrets

from auth import get_current_user, hash_password, verify_password
from db import db
from audit import log as audit_log
from email_service import send_sales_welcome_email, send_commission_payout_email
from config import FRONTEND_URL

router = APIRouter(prefix="/sales", tags=["sales"])


class SalesBusinessOnboardIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=100)
    owner_email: EmailStr
    owner_name: str = Field(..., min_length=2, max_length=100)
    website: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None


class SalesCommissionResponse(BaseModel):
    referral_id: str
    business_id: str
    business_name: str
    owner_email: str
    commission_rate: float
    total_commission_earned: float
    commission_paid: float
    pending_commission: float
    status: str
    last_payment_date: Optional[str]
    created_at: str


class SalesPayoutRequest(BaseModel):
    referral_ids: List[str]
    bank_account_details: str = Field(..., min_length=5, max_length=500)


@router.get("/dashboard")
async def sales_dashboard(user=Depends(get_current_user)):
    """Get sales dashboard with stats and referrals."""
    if user.get("role") not in ("sales", "admin"):
        raise HTTPException(403, "Access denied")
    
    sales_user_id = user["user_id"]
    
    # Get all referrals for this sales user
    referrals = await db.sales_referrals.find({"sales_user_id": sales_user_id}).to_list(length=None)
    
    # Calculate totals
    total_businesses = len(referrals)
    active_paid = sum(1 for r in referrals if r.get("status") == "active")
    total_earned = sum(r.get("total_commission_earned", 0.0) for r in referrals)
    total_paid = sum(r.get("commission_paid", 0.0) for r in referrals)
    pending = sum(r.get("pending_commission", 0.0) for r in referrals)
    
    return {
        "total_businesses": total_businesses,
        "active_paid_subscriptions": active_paid,
        "total_commission_earned": round(total_earned, 2),
        "total_commission_paid": round(total_paid, 2),
        "pending_commission": round(pending, 2),
        "referrals": [SalesCommissionResponse(
            referral_id=r["referral_id"],
            business_id=r["business_id"],
            business_name="",  # Will be populated separately
            owner_email="",
            commission_rate=r["commission_rate"],
            total_commission_earned=r["total_commission_earned"],
            commission_paid=r["commission_paid"],
            pending_commission=r["pending_commission"],
            status=r["status"],
            last_payment_date=r.get("last_payment_date"),
            created_at=r["created_at"]
        ) for r in referrals]
    }


@router.post("/onboard", response_model=dict)
async def onboard_business(payload: SalesBusinessOnboardIn, request: Request, 
                           user=Depends(get_current_user)):
    """Onboard a new business (sales team only)."""
    if user.get("role") != "sales":
        raise HTTPException(403, "Only sales team can onboard businesses")
    
    sales_user_id = user["user_id"]
    
    # Check if email already exists
    existing_owner = await db.users.find_one({"email": payload.owner_email.lower()})
    if existing_owner:
        raise HTTPException(400, "This email is already registered")
    
    # Generate temporary password
    temp_password = secrets.token_urlsafe(12)
    owner_user_id = f"user_{uuid.uuid4().hex[:12]}"
    referral_code = f"ref_{uuid.uuid4().hex[:8]}"
    
    # Create owner user
    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one({
        "user_id": owner_user_id,
        "email": payload.owner_email.lower(),
        "password_hash": hash_password(temp_password),
        "name": payload.owner_name,
        "picture": None,
        "role": "owner",
        "disabled": False,
        "email_verified": False,  # Needs to verify email
        "mfa_enabled": False,
        "mfa_secret": None,
        "referral_code": referral_code,
        "referred_by_code": user.get("referral_code"),  # Track who referred
        "password_changed_at": now,
        "failed_login_count": 0,
        "locked_until": None,
        "created_at": now,
    })
    
    # Create business
    business_id = f"biz_{uuid.uuid4().hex[:12]}"
    await db.businesses.insert_one({
        "business_id": business_id,
        "owner_user_id": owner_user_id,
        "name": payload.business_name,
        "website": payload.website,
        "email": payload.owner_email,
        "phone": payload.phone,
        "category": payload.category,
        "country": payload.country,
        "language": "en",
        "timezone": "UTC",
        "crawl_status": "pending",
        "crawl_progress": 0,
        "knowledge_score": 0,
        "plan": "free",
        "monthly_limit": 100,
        "monthly_used": 0,
        "usage_period": "",
        "overage_count": 0,
        "subscription_status": "active",
        "current_period_end": None,
        "grace_period_ends_at": None,
        "cancel_at_period_end": False,
        "pending_plan_change": None,
        "created_at": now,
    })
    
    # Create sales referral record
    referral_id = f"ref_{uuid.uuid4().hex[:12]}"
    await db.sales_referrals.insert_one({
        "referral_id": referral_id,
        "sales_user_id": sales_user_id,
        "business_id": business_id,
        "commission_rate": 0.15,  # 15%
        "total_commission_earned": 0.0,
        "commission_paid": 0.0,
        "pending_commission": 0.0,
        "status": "active",
        "last_payment_date": None,
        "created_at": now,
    })
    
    # Send welcome email to business owner
    portal_url = FRONTEND_URL or "https://app.roviq.ai"
    await send_sales_welcome_email(payload.owner_email, payload.owner_name, temp_password, portal_url)
    
    await audit_log(request, user["user_id"], "sales.onboarded_business", "business", business_id, {
        "business_name": payload.business_name,
        "owner_email": payload.owner_email,
        "referred_by": user["email"]
    })
    
    return {
        "ok": True,
        "business_id": business_id,
        "message": "Business onboarded successfully. Welcome email sent to owner."
    }


@router.get("/referrals")
async def list_referrals(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List referrals for sales user."""
    if user.get("role") not in ("sales", "admin"):
        raise HTTPException(403, "Access denied")
    
    query = {"sales_user_id": user["user_id"]}
    if status:
        query["status"] = status
    
    referrals = await db.sales_referrals.find(query)\
        .sort("created_at", -1)\
        .skip(skip)\
        .limit(limit)\
        .to_list(length=limit)
    
    # Enrich with business details
    result = []
    for ref in referrals:
        biz = await db.businesses.find_one({"business_id": ref["business_id"]})
        result.append({
            **ref,
            "business_name": biz["name"] if biz else "Unknown",
            "owner_email": biz["email"] if biz else "Unknown",
            "plan": biz["plan"] if biz else "unknown",
            "subscription_status": biz.get("subscription_status", "unknown") if biz else "unknown"
        })
    
    return result


@router.post("/payout", response_model=dict)
async def request_payout(payload: SalesPayoutRequest, request: Request, 
                         user=Depends(get_current_user)):
    """Request commission payout (sales user). Admin approval required."""
    if user.get("role") != "sales":
        raise HTTPException(403, "Only sales team can request payouts")
    
    # Validate referrals belong to this user
    referrals = await db.sales_referrals.find({
        "referral_id": {"$in": payload.referral_ids},
        "sales_user_id": user["user_id"]
    }).to_list(length=len(payload.referral_ids))
    
    if len(referrals) != len(payload.referral_ids):
        raise HTTPException(400, "Some referrals not found or don't belong to you")
    
    # Calculate total pending
    total_pending = sum(r.get("pending_commission", 0.0) for r in referrals)
    if total_pending <= 0:
        raise HTTPException(400, "No pending commission to payout")
    
    # Create payout request for admin approval
    payout_request = {
        "payout_id": f"pay_{uuid.uuid4().hex[:12]}",
        "sales_user_id": user["user_id"],
        "referral_ids": payload.referral_ids,
        "total_amount": total_pending,
        "bank_account_details": payload.bank_account_details,
        "status": "pending",  # pending | approved | paid | rejected
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "paid_at": None,
        "admin_note": None,
    }
    
    await db.payout_requests.insert_one(payout_request)
    
    await audit_log(request, user["user_id"], "sales.payout_requested", "payout", payout_request["payout_id"], {
        "amount": total_pending,
        "referral_count": len(referrals)
    })
    
    return {"ok": True, "payout_id": payout_request["payout_id"], "amount": total_pending}


# Admin endpoints for managing sales team
@router.get("/admin/payout-requests")
async def list_payout_requests(status: Optional[str] = None, user=Depends(get_current_user)):
    """List all payout requests (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    
    query = {}
    if status:
        query["status"] = status
    
    requests = await db.payout_requests.find(query)\
        .sort("requested_at", -1)\
        .to_list(length=100)
    
    # Enrich with sales user info
    result = []
    for req in requests:
        sales_user = await db.users.find_one({"user_id": req["sales_user_id"]})
        result.append({
            **req,
            "sales_user_email": sales_user["email"] if sales_user else "Unknown",
            "sales_user_name": sales_user["name"] if sales_user else "Unknown"
        })
    
    return result


@router.post("/admin/payout/{payout_id}/approve", response_model=dict)
async def approve_payout(payout_id: str, request: Request, user=Depends(get_current_user)):
    """Approve and process payout (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    
    payout = await db.payout_requests.find_one({"payout_id": payout_id})
    if not payout:
        raise HTTPException(404, "Payout request not found")
    
    if payout["status"] != "pending":
        raise HTTPException(400, f"Payout already {payout['status']}")
    
    # Update referrals to mark commission as paid
    now = datetime.now(timezone.utc).isoformat()
    for ref_id in payout["referral_ids"]:
        ref = await db.sales_referrals.find_one({"referral_id": ref_id})
        if ref:
            pending = ref.get("pending_commission", 0.0)
            await db.sales_referrals.update_one(
                {"referral_id": ref_id},
                {"$set": {
                    "commission_paid": ref.get("commission_paid", 0.0) + pending,
                    "pending_commission": 0.0,
                    "last_payment_date": now
                }}
            )
    
    # Mark payout as paid
    await db.payout_requests.update_one(
        {"payout_id": payout_id},
        {"$set": {"status": "paid", "paid_at": now}}
    )
    
    # Notify sales user
    sales_user = await db.users.find_one({"user_id": payout["sales_user_id"]})
    if sales_user and sales_user.get("email"):
        await send_commission_payout_email(
            sales_user["email"],
            sales_user["name"],
            payout["total_amount"],
            len(payout["referral_ids"])
        )
    
    await audit_log(request, user["user_id"], "admin.payout_approved", "payout", payout_id, {
        "amount": payout["total_amount"],
        "sales_user": sales_user["email"] if sales_user else "Unknown"
    })
    
    return {"ok": True, "message": "Payout approved and processed"}


@router.post("/admin/payout/{payout_id}/reject", response_model=dict)
async def reject_payout(payout_id: str, payload: dict, request: Request, user=Depends(get_current_user)):
    """Reject payout request (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    
    payout = await db.payout_requests.find_one({"payout_id": payout_id})
    if not payout:
        raise HTTPException(404, "Payout request not found")
    
    if payout["status"] != "pending":
        raise HTTPException(400, f"Payout already {payout['status']}")
    
    await db.payout_requests.update_one(
        {"payout_id": payout_id},
        {"$set": {"status": "rejected", "admin_note": payload.get("reason", "")}}
    )
    
    await audit_log(request, user["user_id"], "admin.payout_rejected", "payout", payout_id, {})
    
    return {"ok": True}
