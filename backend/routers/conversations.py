from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Optional
import re
from auth import get_current_user
from db import db

router = APIRouter(prefix="/conversations", tags=["conversations"])

VALID_OUTCOMES = {None, "lead", "booked", "resolved", "lost"}


async def _verify(business_id: str, user: dict):
    # Admins don't own any business, but the admin Conversation Explorer drills into
    # conversation detail through this same owner-facing route -- without this bypass
    # that lookup always 404s for them. This doesn't widen what an admin can reach:
    # /admin/conversations already exposes every business's conversations, so this
    # only unblocks the existing admin UI rather than granting a new capability.
    if user.get("role") == "admin":
        biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    else:
        biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz


async def _verify_conv(conversation_id: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Not found")
    await _verify(conv["business_id"], user)
    return conv


@router.get("/business/{business_id}")
async def list_convs(business_id: str, status: Optional[str] = None, unanswered: Optional[bool] = None,
                     archived: Optional[bool] = None, pinned: Optional[bool] = None,
                     search: Optional[str] = None, user=Depends(get_current_user)):
    await _verify(business_id, user)
    q = {"business_id": business_id}
    if status:
        q["status"] = status
    if unanswered is not None:
        q["unanswered"] = unanswered
    # Default view excludes archived conversations, same as an inbox hiding archived mail --
    # pass archived=true explicitly to see them.
    q["archived"] = archived if archived is not None else {"$ne": True}
    if pinned is not None:
        q["pinned"] = pinned

    if search:
        pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
        matching_conv_ids = await db.messages.find(
            {"business_id": business_id, "text": pattern}, {"_id": 0, "conversation_id": 1},
        ).to_list(500)
        conv_ids = {m["conversation_id"] for m in matching_conv_ids}
        q["$or"] = [{"title": pattern}, {"conversation_id": {"$in": list(conv_ids)}}]

    items = await db.conversations.find(q, {"_id": 0}).sort("last_message_at", -1).to_list(200)
    # Pinned conversations surface first regardless of recency, then most-recent-first --
    # matches the mental model of a pinned chat in any chat app.
    items.sort(key=lambda c: (not c.get("pinned", False)))
    return items


@router.get("/{conversation_id}")
async def get_conv(conversation_id: str, user=Depends(get_current_user)):
    conv = await _verify_conv(conversation_id, user)
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
    outcome: Optional[str] = None  # None | lead | booked | resolved | lost


@router.patch("/{conversation_id}/outcome")
async def set_outcome(conversation_id: str, payload: OutcomeIn, user=Depends(get_current_user)):
    """Lets an owner manually tag a conversation as a lead/booking/lost sale/resolved --
    real, owner-confirmed data the owner-chat assistant can analyze for sales/lead trends,
    as opposed to fabricated revenue numbers this app has no source of truth for."""
    if payload.outcome not in VALID_OUTCOMES:
        raise HTTPException(400, f"Invalid outcome, must be one of {sorted(o for o in VALID_OUTCOMES if o)}")
    conv = await _verify_conv(conversation_id, user)
    await db.conversations.update_one({"conversation_id": conversation_id}, {"$set": {"outcome": payload.outcome}})
    return {"ok": True, "outcome": payload.outcome}


class TitleIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/{conversation_id}/title")
async def rename_conv(conversation_id: str, payload: TitleIn, user=Depends(get_current_user)):
    await _verify_conv(conversation_id, user)
    title = payload.title.strip()
    await db.conversations.update_one({"conversation_id": conversation_id},
                                      {"$set": {"title": title, "title_auto_generated": False}})
    return {"ok": True, "title": title}


class PinIn(BaseModel):
    pinned: bool


@router.patch("/{conversation_id}/pin")
async def pin_conv(conversation_id: str, payload: PinIn, user=Depends(get_current_user)):
    await _verify_conv(conversation_id, user)
    await db.conversations.update_one({"conversation_id": conversation_id}, {"$set": {"pinned": payload.pinned}})
    return {"ok": True, "pinned": payload.pinned}


class ArchiveIn(BaseModel):
    archived: bool


@router.patch("/{conversation_id}/archive")
async def archive_conv(conversation_id: str, payload: ArchiveIn, user=Depends(get_current_user)):
    await _verify_conv(conversation_id, user)
    await db.conversations.update_one({"conversation_id": conversation_id}, {"$set": {"archived": payload.archived}})
    return {"ok": True, "archived": payload.archived}


@router.delete("/{conversation_id}")
async def delete_conv(conversation_id: str, user=Depends(get_current_user)):
    await _verify_conv(conversation_id, user)
    await db.messages.delete_many({"conversation_id": conversation_id})
    await db.conversations.delete_one({"conversation_id": conversation_id})
    return {"ok": True}


@router.get("/{conversation_id}/export")
async def export_conv(conversation_id: str, format: str = Query("json", pattern="^(json|txt)$"),
                      user=Depends(get_current_user)):
    conv = await _verify_conv(conversation_id, user)
    msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    fname_base = (conv.get("title") or conversation_id).replace(" ", "_")[:60]

    if format == "txt":
        lines = [f"Conversation: {conv.get('title') or conversation_id}", f"Started: {conv.get('created_at')}", ""]
        for m in msgs:
            who = "Customer" if m["role"] == "user" else "AI"
            lines.append(f"[{m['created_at']}] {who}: {m['text']}")
        body = "\n".join(lines)
        return Response(content=body, media_type="text/plain",
                        headers={"Content-Disposition": f'attachment; filename="{fname_base}.txt"'})

    import json as _json
    payload = {"conversation": conv, "messages": msgs}
    return Response(content=_json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fname_base}.json"'})
