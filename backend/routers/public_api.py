"""External API surface for Business API Keys (see api_keys.py). Authenticated via the
`X-Api-Key` header, not the session cookie -- this is for a business owner's own systems
(e.g. their booking widget on another page, a Zapier/n8n workflow, a nightly export job),
never for browser sessions.

Every route is scoped to exactly the business_id embedded in the key that authenticated
it -- there is no way for a key to name a different business_id, on purpose.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from db import db
from api_keys import require_api_key
import booking
from routers.analytics import compute_summary

router = APIRouter(prefix="/v1", tags=["public-api"])


@router.get("/business")
async def get_business(key=Depends(require_api_key("business:read"))):
    biz = await db.businesses.find_one({"business_id": key["business_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    return {
        "business_id": biz["business_id"], "name": biz["name"], "category": biz.get("category"),
        "website": biz.get("website"), "timezone": biz.get("timezone"), "language": biz.get("language"),
        "plan": biz.get("plan"),
        "appointment_settings": {
            "enabled": biz.get("appointment_settings", {}).get("enabled", False),
            "services": biz.get("appointment_settings", {}).get("services", []),
            "working_hours": biz.get("appointment_settings", {}).get("working_hours", {}),
        },
    }


@router.get("/appointments")
async def list_appointments(status: Optional[str] = Query(None), limit: int = Query(100, le=500),
                            key=Depends(require_api_key("appointments:read"))):
    q = {"business_id": key["business_id"]}
    if status:
        q["status"] = status
    return await db.appointments.find(q, {"_id": 0}).sort("start_time", -1).to_list(limit)


class CreateAppointmentInput(BaseModel):
    service: str
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(description="HH:MM, 24h")
    customer_name: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None


@router.post("/appointments")
async def create_appointment(payload: CreateAppointmentInput, key=Depends(require_api_key("appointments:write"))):
    # Reuses the exact same server-side validation (working hours, double-booking, past-time
    # checks) as the customer-facing chat booking flow -- an API key gets no special trust.
    result = await booking.book(
        key["business_id"], payload.service, payload.date, payload.time,
        payload.customer_name, payload.customer_phone, payload.customer_email,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Could not book that slot"))
    return result


@router.delete("/appointments/{reference}")
async def cancel_appointment(reference: str, key=Depends(require_api_key("appointments:write"))):
    result = await booking.cancel(key["business_id"], reference)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Could not cancel that booking"))
    return result


@router.get("/conversations")
async def list_conversations(limit: int = Query(50, le=200), key=Depends(require_api_key("conversations:read"))):
    return await db.conversations.find(
        {"business_id": key["business_id"]}, {"_id": 0},
    ).sort("last_message_at", -1).to_list(limit)


@router.get("/analytics/summary")
async def analytics_summary(key=Depends(require_api_key("analytics:read"))):
    biz = await db.businesses.find_one({"business_id": key["business_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    return await compute_summary(key["business_id"], biz)
