from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, AsyncGenerator
import uuid
import json
from datetime import datetime, timezone

from db import db
from llm import rag_answer, summarize_conversation, generate_conversation_title, stream_rag_answer
import context_builder
from ratelimit import limiter
import usage
from usage import ensure_current_period
from booking import get_settings as get_booking_settings, BOOKING_SCHEMA, parse_booking, execute_booking_action
from email_sender import send_handoff_email, send_booking_email
from platform_settings import get_settings as get_platform_settings
from services.cache_service import get_redis_client
from services.job_queue import get_job_queue, send_notification_job

router = APIRouter(prefix="/chat", tags=["chat"])

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French",
    "de": "German", "ar": "Arabic", "pt": "Portuguese",
}


async def _generate_and_store_title(conv_id: str, business_name: str, first_message: str):
    title = await generate_conversation_title(business_name, first_message)
    if title:
        # Only overwrite if still auto-generated -- guards against a race where the owner
        # renamed it (e.g. from a fast follow-up message) before this background task ran.
        await db.conversations.update_one(
            {"conversation_id": conv_id, "title_auto_generated": True}, {"$set": {"title": title}},
        )


class ChatIn(BaseModel):
    business_id: str
    visitor_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)


class StreamChatIn(BaseModel):
    business_id: str
    visitor_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)
    stream: bool = True  # Enable SSE streaming


async def generate_chat_stream(payload: ChatIn, biz: dict, settings: dict) -> AsyncGenerator[str, None]:
    """Generate chat response as SSE stream"""
    redis_client = get_redis_client()
    
    try:
        visitor_id = payload.visitor_id or f"vis_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        
        conv_id = payload.conversation_id
        is_new_conversation = not conv_id
        if is_new_conversation:
            conv_id = f"conv_{uuid.uuid4().hex[:12]}"
            await db.conversations.insert_one({
                "conversation_id": conv_id,
                "business_id": payload.business_id,
                "visitor_id": visitor_id,
                "status": "open",
                "unanswered": False,
                "outcome": None,
                "title": None,
                "title_auto_generated": True,
                "pinned": False,
                "archived": False,
                "summary": None,
                "summary_through": 0,
                "created_at": now,
                "last_message_at": now,
                "message_count": 0,
            })
        
        # Store user message
        await db.messages.insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "business_id": payload.business_id,
            "role": "user",
            "text": payload.message,
            "created_at": now,
        })
        
        # Add to Redis conversation cache
        if redis_client.is_available():
            redis_client.add_to_conversation(conv_id, {"role": "user", "text": payload.message})
        
        # Build context
        hits_result = await context_builder.build_context(biz, payload.message, k=6)
        top_score = hits_result["confidence"]
        
        # Get conversation history
        history_docs = await db.messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
        history = [{"role": m["role"], "text": m["text"]} for m in history_docs[:-1]]
        
        # Handle conversation summary for long threads
        prompt_context = hits_result["prompt_context"]
        conv_doc = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0, "message_count": 1, "summary": 1, "summary_through": 1})
        msg_count_so_far = (conv_doc or {}).get("message_count", 0)
        if msg_count_so_far >= 12 and msg_count_so_far - (conv_doc or {}).get("summary_through", 0) >= 10:
            transcript = "\n".join(f"{'Customer' if m['role'] == 'user' else 'AI'}: {m['text']}" for m in history_docs)
            summary = await summarize_conversation(biz["name"], transcript)
            if summary:
                await db.conversations.update_one({"conversation_id": conv_id},
                                                  {"$set": {"summary": summary, "summary_through": msg_count_so_far}})
                conv_doc = {**(conv_doc or {}), "summary": summary, "summary_through": msg_count_so_far}
        if (conv_doc or {}).get("summary"):
            prompt_context = f"=== CONVERSATION SO FAR ===\n{conv_doc['summary']}\n\n{prompt_context}"
        
        booking_settings = await get_booking_settings(payload.business_id)
        booking_block = BOOKING_SCHEMA if booking_settings else ""
        
        unanswered = top_score < float(settings.get("confidence_threshold", 0.6))
        booking_result = None
        
        # Send initial event with conversation info
        yield f"data: {json.dumps({'type': 'start', 'conversation_id': conv_id, 'visitor_id': visitor_id})}\n\n"
        
        # Stream AI response
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
        language = LANGUAGE_NAMES.get(biz.get("language"), None)
        
        full_answer = ""
        async for chunk in stream_rag_answer(
            biz["name"], prompt_context, history, payload.message,
            current_date=today, booking_block=booking_block, language=language
        ):
            full_answer += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        
        # Process booking if detected
        answer, booking_action = parse_booking(full_answer)
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
        
        # Store final AI response
        await db.messages.insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "business_id": payload.business_id,
            "role": "assistant",
            "text": answer,
            "confidence": float(top_score),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        # Update conversation
        await db.conversations.update_one(
            {"conversation_id": conv_id},
            {"$set": {"last_message_at": datetime.now(timezone.utc).isoformat(), "unanswered": unanswered},
             "$inc": {"message_count": 2}}
        )
        
        # Update usage
        inc = {"monthly_used": 1}
        over_limit = biz.get("monthly_used", 0) >= biz.get("monthly_limit", 100)
        overage_billing_on = settings.get("overage_billing_enabled", False) and biz.get("plan") != "free"
        if over_limit and overage_billing_on:
            inc["overage_count"] = 1
        await db.businesses.update_one({"business_id": payload.business_id}, {"$inc": inc})
        
        # Generate title in background if new conversation
        if is_new_conversation:
            background_tasks.add_task(_generate_and_store_title, conv_id, biz["name"], payload.message)
        
        # Cache AI response for deterministic questions
        if redis_client.is_available() and top_score > 0.8:
            import hashlib
            question_hash = hashlib.sha256(payload.message.encode()).hexdigest()[:16]
            redis_client.set_ai_response(payload.business_id, question_hash, answer)
        
        # Send final event
        final_data = {
            'type': 'end',
            'answer': answer,
            'confidence': float(top_score),
            'sources': hits_result['sources'],
            'unanswered': unanswered,
            'booking_result': booking_result
        }
        yield f"data: {json.dumps(final_data)}\n\n"

    except Exception as e:
        logger.error(f"Error in chat stream: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

@router.post("")
@limiter.limit("30/minute")
async def widget_chat(request: Request, payload: ChatIn, background_tasks: BackgroundTasks):
    # Check if streaming is requested
    if hasattr(payload, 'stream') and getattr(payload, 'stream', False):
        return StreamingResponse(
            generate_chat_stream(payload, None, None),
            media_type="text/event-stream"
        )
    
    # Original non-streaming implementation continues below...
    settings = await get_platform_settings()
    if settings.get("maintenance_mode"):
        return {"error": "maintenance", "message": "We're doing some quick maintenance -- please try again in a few minutes."}

    biz = await db.businesses.find_one({"business_id": payload.business_id}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    biz = await ensure_current_period(biz)

    over_limit = biz.get("monthly_used", 0) >= biz.get("monthly_limit", 100)
    overage_billing_on = settings.get("overage_billing_enabled", False) and biz.get("plan") != "free"
    if over_limit and not overage_billing_on:
        return {"error": "limit_reached", "message": "Monthly chat limit reached. Please contact the business owner."}

    visitor_id = payload.visitor_id or f"vis_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    conv_id = payload.conversation_id
    is_new_conversation = not conv_id
    if is_new_conversation:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        await db.conversations.insert_one({
            "conversation_id": conv_id,
            "business_id": payload.business_id,
            "visitor_id": visitor_id,
            "status": "open",
            "unanswered": False,
            "outcome": None,  # None | lead | booked | resolved | lost -- owner-tagged or auto-set on booking
            "title": None,
            "title_auto_generated": True,
            "pinned": False,
            "archived": False,
            "summary": None,
            "summary_through": 0,
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

    hits_result = await context_builder.build_context(biz, payload.message, k=6)
    top_score = hits_result["confidence"]

    history_docs = await db.messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    history = [{"role": m["role"], "text": m["text"]} for m in history_docs[:-1]]

    # Conversation memory: once a thread runs long, the raw last-6-messages window (below)
    # starts losing earlier context -- a name already given, a preference already stated.
    # Maintain a rolling summary instead of resending the whole transcript every turn.
    prompt_context = hits_result["prompt_context"]
    conv_doc = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0, "message_count": 1, "summary": 1, "summary_through": 1})
    msg_count_so_far = (conv_doc or {}).get("message_count", 0)
    if msg_count_so_far >= 12 and msg_count_so_far - (conv_doc or {}).get("summary_through", 0) >= 10:
        transcript = "\n".join(f"{'Customer' if m['role'] == 'user' else 'AI'}: {m['text']}" for m in history_docs)
        summary = await summarize_conversation(biz["name"], transcript)
        if summary:
            await db.conversations.update_one({"conversation_id": conv_id},
                                              {"$set": {"summary": summary, "summary_through": msg_count_so_far}})
            conv_doc = {**(conv_doc or {}), "summary": summary, "summary_through": msg_count_so_far}
    if (conv_doc or {}).get("summary"):
        prompt_context = f"=== CONVERSATION SO FAR ===\n{conv_doc['summary']}\n\n{prompt_context}"

    booking_settings = await get_booking_settings(payload.business_id)
    booking_block = BOOKING_SCHEMA if booking_settings else ""

    unanswered = top_score < float(settings.get("confidence_threshold", 0.6))
    booking_result = None
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
        language = LANGUAGE_NAMES.get(biz.get("language"), None)
        raw_answer = await rag_answer(biz["name"], prompt_context, history, payload.message,
                                      current_date=today, booking_block=booking_block, language=language)
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
    inc = {"monthly_used": 1}
    if over_limit and overage_billing_on:
        inc["overage_count"] = 1
    await db.businesses.update_one({"business_id": payload.business_id}, {"$inc": inc})
    background_tasks.add_task(usage.maybe_send_quota_alert, biz, biz.get("monthly_used", 0) + 1)

    if is_new_conversation:
        background_tasks.add_task(_generate_and_store_title, conv_id, biz["name"], payload.message)

    return {
        "conversation_id": conv_id,
        "visitor_id": visitor_id,
        "answer": answer,
        "confidence": float(top_score),
        "sources": hits_result["sources"],
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


@router.get("/business/{business_id}/landing-page")
async def landing_page_data(business_id: str):
    """Public data for the standalone hosted chat page (TalkPage.jsx) -- deliberately a
    separate, richer endpoint from widget-config above rather than bloating that one,
    since widget-config is fetched on every page the floating widget embeds on across the
    internet and should stay minimal; this is fetched once per landing-page visit."""
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")

    settings = await get_platform_settings()
    widget = dict(biz.get("widget", {}))
    if biz.get("plan", "free") == "free" and settings.get("watermark_required_on_free", True):
        widget["show_branding"] = True

    published_legal = await db.legal_documents.find(
        {"is_published": True}, {"_id": 0, "doc_type": 1, "title": 1},
    ).to_list(20)

    appt = biz.get("appointment_settings") or {}
    faqs = []
    chunks = await db.knowledge_chunks.find(
        {"business_id": business_id, "source_type": "faq"}, {"_id": 0, "source_title": 1, "text": 1},
    ).to_list(12)
    for c in chunks:
        # stored as "Q: ...\nA: ..." (see actions.py/knowledge.py) -- split back into a
        # clean question/answer pair for display rather than showing the raw Q:/A: text
        text = c.get("text", "")
        if text.startswith("Q:") and "\nA:" in text:
            q, a = text[2:].split("\nA:", 1)
            faqs.append({"question": q.strip(), "answer": a.strip()})
        else:
            faqs.append({"question": c.get("source_title", "Question"), "answer": text})

    return {
        "business_id": business_id,
        "business_name": biz["name"],
        "category": biz.get("category"),
        "website": biz.get("website"),
        "phone": biz.get("phone"),
        "email": biz.get("email"),
        "quick_facts": biz.get("quick_facts") or {},
        "widget": widget,
        "plan": biz.get("plan", "free"),
        "appointment_settings": ({
            "enabled": True,
            "services": appt.get("services", []),
            "working_hours": appt.get("working_hours", {}),
        } if appt.get("enabled") else {"enabled": False}),
        "timezone": biz.get("timezone", "UTC"),
        "faqs": faqs,
        "testimonials": biz.get("testimonials") or [],
        "legal_docs": published_legal,
        "platform_support_email": settings.get("support_email") or None,
        "platform_company_name": settings.get("company_legal_name") or None,
    }
