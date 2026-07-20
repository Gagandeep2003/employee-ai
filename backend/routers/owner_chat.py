from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from db import db
from llm import owner_chat_reply
from actions import ACTION_SCHEMAS, parse_action, execute_action
from ratelimit import limiter

router = APIRouter(prefix="/owner-chat", tags=["owner-chat"])


class Ask(BaseModel):
    business_id: str
    question: str = Field(min_length=1, max_length=2000)


@router.post("/ask")
@limiter.limit("20/minute")
async def ask(request: Request, payload: Ask, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": payload.business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")

    # Build data snapshot
    total_conv = await db.conversations.count_documents({"business_id": payload.business_id})
    unanswered = await db.conversations.count_documents({"business_id": payload.business_id, "unanswered": True})
    escalated = await db.conversations.count_documents({"business_id": payload.business_id, "status": "escalated"})
    leads = await db.conversations.count_documents({"business_id": payload.business_id, "outcome": "lead"})
    booked = await db.conversations.count_documents({"business_id": payload.business_id, "outcome": "booked"})
    lost = await db.conversations.count_documents({"business_id": payload.business_id, "outcome": "lost"})
    upcoming_appts = await db.appointments.count_documents({"business_id": payload.business_id, "status": "confirmed"})
    recent = await db.messages.find({"business_id": payload.business_id, "role": "user"}, {"text": 1, "_id": 0}).sort("created_at", -1).limit(15).to_list(15)
    kb_count = await db.knowledge_chunks.count_documents({"business_id": payload.business_id})
    appt_settings = biz.get("appointment_settings") or {}

    profile = (
        f"Business ID: {biz['business_id']}\n"
        f"Name: {biz['name']} | Category: {biz.get('category') or '-'}\n"
        f"Website: {biz.get('website') or '-'} | Email: {biz.get('email') or '-'} | Phone: {biz.get('phone') or '-'}\n"
        f"Country: {biz.get('country') or '-'} | Language: {biz.get('language')} | Timezone: {biz.get('timezone')}\n"
        f"Plan: {biz.get('plan')} | Usage: {biz.get('monthly_used',0)}/{biz.get('monthly_limit',100)}\n"
        f"Widget: color={biz.get('widget',{}).get('primary_color')} welcome=\"{biz.get('widget',{}).get('welcome_message','')[:60]}\"\n"
        f"Knowledge chunks: {kb_count} | Knowledge Score: {biz.get('knowledge_score',0)}\n"
        f"Conversations (all-time): {total_conv} | Unanswered: {unanswered} | Escalated: {escalated}\n"
        f"Leads (tagged by you): {leads} | Bookings from chat: {booked} | Lost: {lost}\n"
        f"Appointment booking: {'ON' if appt_settings.get('enabled') else 'OFF'} | Upcoming appointments: {upcoming_appts}\n"
    )
    recent_q = "\n".join(f"- {m['text']}" for m in recent) if recent else "(none)"

    system = (
        f"You are the AI Employee for the OWNER of '{biz['name']}'. You are the owner's private ops assistant. "
        "You have TWO capabilities:\n"
        "(a) READ - analyze data, summarize conversations, spot trends, suggest improvements.\n"
        "(b) WRITE - perform actions on the business (see action schema below) when the owner asks.\n"
        "The customer-facing AI is a separate persona that only reads. You, however, can update business info, edit knowledge, "
        "customize the widget, and teach the AI new answers. This is a private, authenticated conversation with the verified "
        "owner of this business only -- there is no customer input mixed into this prompt.\n\n"
        "Be concise. Use short paragraphs or bullet points. Never invent data -- only use the DATA SNAPSHOT below.\n\n"
        f"=== DATA SNAPSHOT ===\n{profile}\n"
        f"Recent customer questions:\n{recent_q}\n"
        f"=== END SNAPSHOT ===\n\n"
        f"{ACTION_SCHEMAS}"
    )
    try:
        raw = await owner_chat_reply(system, payload.question)
    except Exception as e:
        raise HTTPException(502, f"AI service unavailable, please try again: {e}")

    text, action = parse_action(raw)
    result = None
    if action:
        result = await execute_action(payload.business_id, action)

    return {"answer": text, "action": action, "result": result}
