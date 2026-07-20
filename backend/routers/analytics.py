from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from auth import get_current_user
from db import db
from collections import Counter

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _verify(business_id: str, user: dict):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz


@router.get("/business/{business_id}/summary")
async def summary(business_id: str, user=Depends(get_current_user)):
    biz = await _verify(business_id, user)
    total_conv = await db.conversations.count_documents({"business_id": business_id})
    total_msgs = await db.messages.count_documents({"business_id": business_id})
    unanswered = await db.conversations.count_documents({"business_id": business_id, "unanswered": True})
    escalated = await db.conversations.count_documents({"business_id": business_id, "status": "escalated"})

    # last 7 days
    now = datetime.now(timezone.utc)
    days = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        end = (datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
        c = await db.conversations.count_documents({"business_id": business_id, "created_at": {"$gte": start, "$lt": end}})
        days.append({"day": day.strftime("%a"), "date": day.isoformat(), "conversations": c})

    # popular topics (word freq from user messages)
    user_msgs = await db.messages.find({"business_id": business_id, "role": "user"}, {"text": 1, "_id": 0}).limit(500).to_list(500)
    words = []
    stop = set("i you the a an is are be to of and for in on with what how why can do does when where who our my your this that if it".split())
    for m in user_msgs:
        for w in m["text"].lower().split():
            w = "".join(ch for ch in w if ch.isalnum())
            if len(w) > 3 and w not in stop:
                words.append(w)
    top_topics = [{"word": w, "count": c} for w, c in Counter(words).most_common(10)]

    # Lead/booking conversion -- real, owner-confirmed or auto-set-on-booking data only
    # (no fabricated revenue/profit numbers; see conversations.py PATCH /outcome).
    leads = await db.conversations.count_documents({"business_id": business_id, "outcome": "lead"})
    booked = await db.conversations.count_documents({"business_id": business_id, "outcome": "booked"})
    lost = await db.conversations.count_documents({"business_id": business_id, "outcome": "lost"})
    upcoming_appointments = await db.appointments.count_documents({"business_id": business_id, "status": "confirmed"})

    accuracy = 0 if not total_msgs else round(100 * (1 - unanswered / max(total_conv, 1)))
    return {
        "total_conversations": total_conv,
        "total_messages": total_msgs,
        "unanswered": unanswered,
        "escalated": escalated,
        "accuracy_pct": accuracy,
        "monthly_used": biz.get("monthly_used", 0),
        "monthly_limit": biz.get("monthly_limit", 100),
        "knowledge_score": biz.get("knowledge_score", 0),
        "days": days,
        "top_topics": top_topics,
        "leads": leads,
        "bookings": booked,
        "lost": lost,
        "upcoming_appointments": upcoming_appointments,
    }
