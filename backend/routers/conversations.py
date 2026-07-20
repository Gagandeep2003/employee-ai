from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from auth import get_current_user
from db import db

router = APIRouter(prefix="/conversations", tags=["conversations"])

VALID_OUTCOMES = {None, "lead", "booked", "resolved", "lost"}


async def _verify(business_id: str, user: dict):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz


@router.get("/business/{business_id}")
async def list_convs(business_id: str, status: str | None = None, unanswered: bool | None = None,
                     user=Depends(get_current_user)):
    await _verify(business_id, user)
    q = {"business_id": business_id}
    if status:
        q["status"] = status
    if unanswered is not None:
        q["unanswered"] = unanswered
    items = await db.conversations.find(q, {"_id": 0}).sort("last_message_at", -1).to_list(200)
    return items


@router.get("/{conversation_id}")
async def get_conv(conversation_id: str, user=Depends(get_current_user)):
    conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Not found")
    await _verify(conv["business_id"], user)
    msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"conversation": conv, "messages": msgs}


@router.get("/business/{business_id}/unanswered")
async def unanswered_questions(business_id: str, user=Depends(get_current_user)):
    await _verify(business_id, user)
    # find user messages in conversations flagged unanswered
    convs = await db.conversations.find({"business_id": business_id, "unanswered": True}, {"_id": 0}).sort("last_message_at", -1).to_list(200)
    out = []
    for c in convs:
        last_user = await db.messages.find_one({"conversation_id": c["conversation_id"], "role": "user"},
                                               {"_id": 0}, sort=[("created_at", -1)])
        if last_user:
            out.append({"conversation_id": c["conversation_id"], "question": last_user["text"],
                        "created_at": last_user["created_at"]})
    return out


@router.get("/business/{business_id}/notifications")
async def notifications(business_id: str, user=Depends(get_current_user)):
    await _verify(business_id, user)
    items = await db.notifications.find({"business_id": business_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return items


class OutcomeIn(BaseModel):
    outcome: str | None  # None | lead | booked | resolved | lost


@router.patch("/{conversation_id}/outcome")
async def set_outcome(conversation_id: str, payload: OutcomeIn, user=Depends(get_current_user)):
    """Lets an owner manually tag a conversation as a lead/booking/lost sale/resolved --
    real, owner-confirmed data the owner-chat assistant can analyze for sales/lead trends,
    as opposed to fabricated revenue numbers this app has no source of truth for."""
    if payload.outcome not in VALID_OUTCOMES:
        raise HTTPException(400, f"Invalid outcome, must be one of {sorted(o for o in VALID_OUTCOMES if o)}")
    conv = await db.conversations.find_one({"conversation_id": conversation_id})
    if not conv:
        raise HTTPException(404, "Not found")
    await _verify(conv["business_id"], user)
    await db.conversations.update_one({"conversation_id": conversation_id}, {"$set": {"outcome": payload.outcome}})
    return {"ok": True, "outcome": payload.outcome}
