from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime, timezone

from db import db
from retrieval import search
from llm import rag_answer
from ratelimit import limiter
from usage import ensure_current_period
from booking import get_settings as get_booking_settings, describe_settings as describe_booking, \
    parse_booking, execute_booking_action, BOOKING_SCHEMA
from email_sender import send_handoff_email, send_booking_email
from platform_settings import get_settings as get_platform_settings
from freshness import days_since

router = APIRouter(prefix="/chat", tags=["chat"])

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French",
    "de": "German", "ar": "Arabic", "pt": "Portuguese",
}


class ChatIn(BaseModel):
    business_id: str
    visitor_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)


@router.post("")
@limiter.limit("30/minute")
async def widget_chat(request: Request, payload: ChatIn):
    settings = await get_platform_settings()
    if settings.get("maintenance_mode"):
        return {"error": "maintenance", "message": "We're doing some quick maintenance -- please try again in a few minutes."}

    biz = await db.businesses.find_one({"business_id": payload.business_id}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    biz = await ensure_current_period(biz)

    if biz.get("monthly_used", 0) >= biz.get("monthly_limit", 100):
        return {"error": "limit_reached", "message": "Monthly chat limit reached. Please contact the business owner."}

    visitor_id = payload.visitor_id or f"vis_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    conv_id = payload.conversation_id
    if not conv_id:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        await db.conversations.insert_one({
            "conversation_id": conv_id,
            "business_id": payload.business_id,
            "visitor_id": visitor_id,
            "status": "open",
            "unanswered": False,
            "outcome": None,  # None | lead | booked | resolved | lost -- owner-tagged or auto-set on booking
            "created_at": now,
            "last_message_at": now,
            "message_count": 0,
        })

    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "conversation_id": conv_id,
        "business_id": payload.business_id,
        "role": "user",
        "text": payload.message,
        "created_at": now,
    })

    hits = await search(payload.business_id, payload.message, k=5)
    top_score = hits[0][1] if hits else 0.0

    def _fmt_source(h):
        chunk = h[0]
        age = days_since(chunk.get("created_at"))
        age_note = "today" if age == 0 else f"{age}d ago" if age < 9999 else "unknown age"
        title = chunk.get("source_title") or chunk.get("source")
        return f"[{title}, updated {age_note}]\n{chunk['text']}"

    context = "\n\n".join(_fmt_source(h) for h in hits) or "(No knowledge available yet.)"

    quick_facts = biz.get("quick_facts") or {}
    live_lines = [v for k, v in (
        ("hours_note", quick_facts.get("hours_note")),
        ("special_or_promo", quick_facts.get("special_or_promo")),
        ("announcement", quick_facts.get("announcement")),
    ) if v]
    live_info = ""
    if live_lines:
        qf_age = days_since(quick_facts.get("updated_at"))
        live_info = ("LIVE INFO (set directly by the owner, " + (f"{qf_age}d ago" if qf_age < 9999 else "recently") +
                     " -- this is more current than anything in CONTEXT below and should be trusted over it "
                     "if they conflict):\n" + "\n".join(f"- {line}" for line in live_lines) + "\n")

    history_docs = await db.messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).to_list(20)
    history = [{"role": m["role"], "text": m["text"]} for m in history_docs[:-1]]

    booking_settings = await get_booking_settings(payload.business_id)
    booking_block = f"{BOOKING_SCHEMA}\n{describe_booking(booking_settings)}" if booking_settings else ""

    unanswered = top_score < float(settings.get("confidence_threshold", 0.6)) or not hits
    booking_result = None
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
        language = LANGUAGE_NAMES.get(biz.get("language"), None)
        raw_answer = await rag_answer(biz["name"], context, history, payload.message,
                                      current_date=today, booking_block=booking_block, language=language,
                                      live_info=live_info)
        answer, booking_action = parse_booking(raw_answer)
        if booking_action and booking_settings:
            booking_result = await execute_booking_action(payload.business_id, booking_action, conv_id)
            if booking_result.get("ok"):
                if booking_action.get("type") == "book":
                    answer += (f"\n\n✅ Confirmed! Reference **{booking_result['reference']}** for "
                              f"{booking_result['service']} on {booking_result['start_time'][:16].replace('T', ' at ')}.")
                    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"outcome": "booked"}})
                    owner_email = biz.get("email")
                    if owner_email:
                        await send_booking_email(owner_email, biz["name"], booking_result["service"],
                                                 booking_result["start_time"], booking_result["customer_name"],
                                                 booking_result.get("customer_phone"), booking_result.get("customer_email"),
                                                 booking_result["reference"])
                elif booking_action.get("type") == "check_availability":
                    slots = booking_result.get("slots") or []
                    answer += ("\n\nOpen times: " + ", ".join(slots)) if slots else "\n\nNo open slots that day, sorry!"
                elif booking_action.get("type") == "cancel":
                    answer += "\n\n✅ That booking has been cancelled."
            else:
                answer += f"\n\n⚠️ {booking_result.get('error', 'Something went wrong with that booking.')}"
        unanswered = unanswered and not (booking_result and booking_result.get("ok"))
    except Exception:
        answer = "Sorry -- I'm having trouble reaching my knowledge right now. Would you like me to connect you with a human?"
        unanswered = True

    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "conversation_id": conv_id,
        "business_id": payload.business_id,
        "role": "assistant",
        "text": answer,
        "confidence": float(top_score),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    await db.conversations.update_one(
        {"conversation_id": conv_id},
        {"$set": {"last_message_at": datetime.now(timezone.utc).isoformat(), "unanswered": unanswered},
         "$inc": {"message_count": 2}}
    )
    await db.businesses.update_one({"business_id": payload.business_id}, {"$inc": {"monthly_used": 1}})

    return {
        "conversation_id": conv_id,
        "visitor_id": visitor_id,
        "answer": answer,
        "confidence": float(top_score),
        "sources": [{"title": h[0].get("source_title"), "source": h[0].get("source")} for h in hits[:3]],
        "unanswered": unanswered,
    }


class HandoffIn(BaseModel):
    business_id: str
    conversation_id: str
    visitor_email: Optional[str] = None
    visitor_name: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=1000)


@router.post("/handoff")
@limiter.limit("10/minute")
async def request_human(request: Request, payload: HandoffIn):
    conv = await db.conversations.find_one({"conversation_id": payload.conversation_id})
    if not conv or conv.get("business_id") != payload.business_id:
        raise HTTPException(404, "Conversation not found")
    await db.conversations.update_one({"conversation_id": payload.conversation_id},
                                      {"$set": {"status": "escalated", "outcome": "lead"}})
    notif = {
        "id": str(uuid.uuid4()),
        "business_id": payload.business_id,
        "type": "handoff",
        "conversation_id": payload.conversation_id,
        "visitor_email": payload.visitor_email,
        "visitor_name": payload.visitor_name,
        "note": payload.note,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one(notif)

    biz = await db.businesses.find_one({"business_id": payload.business_id}, {"_id": 0, "email": 1, "name": 1})
    if biz and biz.get("email"):
        await send_handoff_email(biz["email"], biz["name"], payload.visitor_name, payload.visitor_email,
                                 payload.note, payload.conversation_id)
    return {"ok": True}


@router.get("/business/{business_id}/widget-config")
async def widget_config(business_id: str):
    """Public endpoint for the widget to fetch config (colors, welcome msg)."""
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    widget = dict(biz.get("widget", {}))
    # Branding removal is a paid feature -- enforced here, the one place the widget
    # actually reads its config from, so it can't be bypassed by editing the stored
    # value directly or via the owner-chat AI's update_widget action. Admins can turn
    # this requirement off platform-wide from /admin/settings.
    settings = await get_platform_settings()
    if biz.get("plan", "free") == "free" and settings.get("watermark_required_on_free", True):
        widget["show_branding"] = True
    return {
        "business_id": business_id,
        "business_name": biz["name"],
        "widget": widget,
        "plan": biz.get("plan", "free"),
    }
