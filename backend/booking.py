"""Customer-facing appointment booking.

This is intentionally a SEPARATE, much more restrictive action grammar from
actions.py (the owner's action set). The owner's actions run for an
authenticated business owner and can rewrite business data; anything reachable
from the anonymous public /chat endpoint must be narrowly scoped and always
re-validated server-side -- the model's understanding of "is this slot free"
is never trusted on its own, every booking is re-checked against real data
right before it's written.
"""
import re
import json
import uuid
from datetime import datetime, timedelta, date as date_cls, timezone as tz

from db import db

BOOKING_RE = re.compile(r"<booking>\s*(\{.*?\})\s*</booking>", re.DOTALL)

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

BOOKING_SCHEMA = """APPOINTMENT BOOKING: this business has appointment booking enabled. If the customer
wants to book, check availability for, or cancel an appointment, you may emit ONE booking
action at the very end of your reply (after your normal reply text):

To check open times for a day:
<booking>{"type": "check_availability", "service": "<exact service name>", "date": "YYYY-MM-DD"}</booking>

To book (only once you have the customer's name and a phone or email):
<booking>{"type": "book", "service": "<exact service name>", "date": "YYYY-MM-DD", "time": "HH:MM", "customer_name": "...", "customer_phone": "...", "customer_email": "..."}</booking>

To cancel (the customer must give you their reference code, e.g. APT-AB12CD):
<booking>{"type": "cancel", "booking_reference": "..."}</booking>

Rules:
- Only use service names exactly as listed below. Never invent a service or a price.
- Ask for the customer's name and (phone or email) before booking -- ask for whichever is missing, one action per turn.
- Resolve relative dates ("tomorrow", "next Monday") into YYYY-MM-DD using the CURRENT DATE given above.
- Do not tell the customer a booking is confirmed yourself -- the system checks real availability and confirms or rejects it; just emit the action and let the result speak for itself next turn.
"""


def parse_booking(text: str):
    m = BOOKING_RE.search(text)
    if not m:
        return text.strip(), None
    try:
        b = json.loads(m.group(1))
    except Exception:
        return text.strip(), None
    clean = BOOKING_RE.sub("", text).strip()
    return clean, b


def _parse_hhmm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def _day_key(d: date_cls) -> str:
    return DAY_KEYS[d.weekday()]


async def get_settings(business_id: str):
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0, "appointment_settings": 1})
    settings = (biz or {}).get("appointment_settings") or {}
    return settings if settings.get("enabled") else None


def describe_settings(settings: dict) -> str:
    """Human-readable block injected into the customer-chat system prompt."""
    if not settings:
        return ""
    services = settings.get("services", [])
    svc_lines = "\n".join(f"  - {s['name']} ({s.get('duration_minutes', 30)} min)" for s in services)
    hours = settings.get("working_hours", {})
    hour_lines = "\n".join(
        f"  - {k}: {v[0]}-{v[1]}" if v else f"  - {k}: closed"
        for k, v in [(d, hours.get(d)) for d in DAY_KEYS]
    )
    return f"Services offered:\n{svc_lines}\n\nWorking hours (24h):\n{hour_lines}\n"


async def get_open_slots(business_id: str, service: str, date_str: str) -> dict:
    settings = await get_settings(business_id)
    if not settings:
        return {"ok": False, "error": "Appointment booking is not enabled for this business"}
    services = {s["name"]: s for s in settings.get("services", [])}
    if service not in services:
        return {"ok": False, "error": f"Unknown service '{service}'"}
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"ok": False, "error": "Invalid date format, expected YYYY-MM-DD"}
    if d < datetime.now(tz.utc).date():
        return {"ok": False, "error": "That date is in the past"}

    hours = (settings.get("working_hours") or {}).get(_day_key(d))
    if not hours:
        return {"ok": True, "slots": [], "note": "Closed that day"}
    start_h, start_m = _parse_hhmm(hours[0])
    end_h, end_m = _parse_hhmm(hours[1])
    interval = int(settings.get("slot_interval_minutes", 30))
    duration = int(services[service].get("duration_minutes", interval))

    day_start = datetime(d.year, d.month, d.day, start_h, start_m, tzinfo=tz.utc)
    day_end = datetime(d.year, d.month, d.day, end_h, end_m, tzinfo=tz.utc)

    existing = await db.appointments.find({
        "business_id": business_id, "status": "confirmed",
        "start_time": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()},
    }, {"_id": 0, "start_time": 1, "end_time": 1}).to_list(200)
    busy = [(datetime.fromisoformat(e["start_time"]), datetime.fromisoformat(e["end_time"])) for e in existing]

    slots = []
    cur = day_start
    while cur + timedelta(minutes=duration) <= day_end:
        slot_end = cur + timedelta(minutes=duration)
        if not any(cur < b_end and slot_end > b_start for b_start, b_end in busy):
            slots.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=interval)
    return {"ok": True, "slots": slots}


async def book(business_id: str, service: str, date_str: str, time_str: str,
               customer_name: str, customer_phone: str = None, customer_email: str = None,
               conversation_id: str = None) -> dict:
    if not customer_name or not (customer_phone or customer_email):
        return {"ok": False, "error": "Need the customer's name and a phone or email to confirm"}
    settings = await get_settings(business_id)
    if not settings:
        return {"ok": False, "error": "Appointment booking is not enabled for this business"}
    services = {s["name"]: s for s in settings.get("services", [])}
    if service not in services:
        return {"ok": False, "error": f"Unknown service '{service}'"}
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        h, m = _parse_hhmm(time_str)
    except ValueError:
        return {"ok": False, "error": "Invalid date/time format"}

    start = datetime(d.year, d.month, d.day, h, m, tzinfo=tz.utc)
    if start < datetime.now(tz.utc):
        return {"ok": False, "error": "That time is in the past"}
    duration = int(services[service].get("duration_minutes", settings.get("slot_interval_minutes", 30)))
    end = start + timedelta(minutes=duration)

    hours = (settings.get("working_hours") or {}).get(_day_key(d))
    if not hours:
        return {"ok": False, "error": "Closed that day"}
    open_h, open_m = _parse_hhmm(hours[0])
    close_h, close_m = _parse_hhmm(hours[1])
    day_start = datetime(d.year, d.month, d.day, open_h, open_m, tzinfo=tz.utc)
    day_end = datetime(d.year, d.month, d.day, close_h, close_m, tzinfo=tz.utc)
    if start < day_start or end > day_end:
        return {"ok": False, "error": "Outside working hours"}

    clash = await db.appointments.find_one({
        "business_id": business_id, "status": "confirmed",
        "start_time": {"$lt": end.isoformat()}, "end_time": {"$gt": start.isoformat()},
    })
    if clash:
        return {"ok": False, "error": "That slot was just taken -- please choose another time"}

    ref = f"APT-{uuid.uuid4().hex[:6].upper()}"
    await db.appointments.insert_one({
        "id": str(uuid.uuid4()),
        "reference": ref,
        "business_id": business_id,
        "service": service,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "status": "confirmed",
        "conversation_id": conversation_id,
        "created_at": datetime.now(tz.utc).isoformat(),
    })
    return {"ok": True, "reference": ref, "start_time": start.isoformat(), "service": service,
            "customer_name": customer_name, "customer_phone": customer_phone, "customer_email": customer_email}


async def cancel(business_id: str, reference: str) -> dict:
    if not reference:
        return {"ok": False, "error": "booking_reference required"}
    res = await db.appointments.update_one(
        {"business_id": business_id, "reference": reference.strip().upper(), "status": "confirmed"},
        {"$set": {"status": "cancelled"}}
    )
    if res.modified_count == 0:
        return {"ok": False, "error": "Booking reference not found or already cancelled"}
    return {"ok": True}


async def execute_booking_action(business_id: str, action: dict, conversation_id: str = None) -> dict:
    atype = action.get("type")
    if atype == "check_availability":
        return await get_open_slots(business_id, action.get("service", ""), action.get("date", ""))
    if atype == "book":
        return await book(business_id, action.get("service", ""), action.get("date", ""), action.get("time", ""),
                          action.get("customer_name", ""), action.get("customer_phone"), action.get("customer_email"),
                          conversation_id)
    if atype == "cancel":
        return await cancel(business_id, action.get("booking_reference", ""))
    return {"ok": False, "error": f"Unknown booking action: {atype}"}
