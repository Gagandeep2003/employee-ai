from fastapi import APIRouter, Depends
from auth import get_current_user
from db import db

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/mine")
async def mine(user=Depends(get_current_user)):
    invited = await db.users.count_documents({"referred_by_code": user["referral_code"]})
    rewarded = await db.referrals.count_documents({"code": user["referral_code"], "status": "rewarded"})
    items = await db.referrals.find({"code": user["referral_code"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "referral_code": user["referral_code"],
        "invited": invited,
        "rewarded": rewarded,
        "discount_active": rewarded > 0,
        "discount_pct": 25 if rewarded > 0 else 0,
        "items": items,
    }
