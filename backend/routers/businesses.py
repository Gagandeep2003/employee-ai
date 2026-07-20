from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timezone

from auth import get_current_user
from db import db
from crawler import crawl_site
from retrieval import tokenize, invalidate
from usage import current_period
from llm import generate_business_snapshot
from platform_settings import get_settings as get_platform_settings, get_plan_limit
from routers.billing import PLANS
from freshness import touch as touch_knowledge

router = APIRouter(prefix="/businesses", tags=["businesses"])

DEFAULT_APPOINTMENT_SETTINGS = {
    "enabled": False,
    "services": [],  # [{"name": str, "duration_minutes": int}]
    "working_hours": {d: None for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
    "slot_interval_minutes": 30,
}

DEFAULT_QUICK_FACTS = {
    "hours_note": "",
    "special_or_promo": "",
    "announcement": "",
    "updated_at": None,
}


class BusinessCreate(BaseModel):
    name: str
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    language: str = "en"
    timezone: str = "UTC"


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    widget: Optional[dict] = None


class AppointmentSettingsIn(BaseModel):
    enabled: bool = False
    services: List[Dict[str, Any]] = Field(default_factory=list)
    working_hours: Dict[str, Optional[List[str]]] = Field(default_factory=dict)
    slot_interval_minutes: int = 30


def _knowledge_score(chunk_count: int, biz: dict) -> int:
    score = 0
    score += min(50, chunk_count * 2)
    for f in ["website", "email", "phone", "category", "country"]:
        if biz.get(f): score += 10
    return min(score, 100)


async def _generate_snapshot(business_id: str):
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    if not biz:
        return
    texts = await db.knowledge_chunks.find(
        {"business_id": business_id}, {"_id": 0, "text": 1}
    ).sort("created_at", -1).to_list(40)
    combined = "\n\n".join(t["text"] for t in texts)
    if not combined.strip():
        return
    snapshot = await generate_business_snapshot(biz["name"], biz.get("category"), combined)
    if snapshot:
        await db.businesses.update_one(
            {"business_id": business_id},
            {"$set": {"ai_snapshot": snapshot, "ai_snapshot_generated_at": datetime.now(timezone.utc).isoformat()}}
        )


async def _run_crawl(business_id: str, website: str):
    try:
        await db.businesses.update_one({"business_id": business_id},
                                       {"$set": {"crawl_status": "crawling", "crawl_progress": 10}})
        chunks = await crawl_site(website, max_pages=int((await get_platform_settings()).get("crawl_max_pages", 15)))
        docs = []
        for url, title, text in chunks:
            docs.append({
                "id": str(uuid.uuid4()),
                "business_id": business_id,
                "text": text,
                "source": url,
                "source_title": title,
                "tokens": tokenize(text),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        if docs:
            await db.knowledge_chunks.insert_many(docs)
        invalidate(business_id)
        biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
        total_chunks = await db.knowledge_chunks.count_documents({"business_id": business_id})
        score = _knowledge_score(total_chunks, biz or {})
        await db.businesses.update_one({"business_id": business_id},
                                       {"$set": {"crawl_status": "done", "crawl_progress": 100,
                                                 "knowledge_score": score}})
        await touch_knowledge(business_id)
        await _generate_snapshot(business_id)
    except Exception:
        await db.businesses.update_one({"business_id": business_id},
                                       {"$set": {"crawl_status": "error", "crawl_progress": 0}})


@router.post("")
async def create_business(payload: BusinessCreate, bg: BackgroundTasks, user=Depends(get_current_user)):
    bid = f"biz_{uuid.uuid4().hex[:12]}"
    free_limit = await get_plan_limit("free", PLANS["free"]["limit"])
    doc = {
        "business_id": bid,
        "owner_user_id": user["user_id"],
        "name": payload.name,
        "website": payload.website,
        "email": payload.email,
        "phone": payload.phone,
        "category": payload.category,
        "country": payload.country,
        "language": payload.language,
        "timezone": payload.timezone,
        "crawl_status": "pending" if payload.website else "done",
        "crawl_progress": 0,
        "knowledge_score": 0,
        "ai_snapshot": None,
        "ai_snapshot_generated_at": None,
        "plan": "free",
        "monthly_limit": free_limit,
        "monthly_used": 0,
        "usage_period": current_period(),
        "appointment_settings": dict(DEFAULT_APPOINTMENT_SETTINGS),
        "quick_facts": dict(DEFAULT_QUICK_FACTS),
        "knowledge_last_updated_at": datetime.now(timezone.utc).isoformat(),
        "last_nudge_sent_at": None,
        "widget": {
            "primary_color": "#1E3F33",
            "accent_color": "#C4A47C",
            "welcome_message": f"Hi! I'm the AI Employee for {payload.name}. How can I help?",
            "position": "bottom-right",
            "logo_url": None,
            "show_branding": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.businesses.insert_one(doc)
    if payload.website:
        bg.add_task(_run_crawl, bid, payload.website)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_businesses(user=Depends(get_current_user)):
    items = await db.businesses.find({"owner_user_id": user["user_id"]}, {"_id": 0}).to_list(50)
    return items


@router.get("/{business_id}")
async def get_business(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz


@router.patch("/{business_id}")
async def update_business(business_id: str, payload: BusinessUpdate, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        await db.businesses.update_one({"business_id": business_id}, {"$set": updates})
    doc = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    return doc


@router.post("/{business_id}/recrawl")
async def recrawl(business_id: str, bg: BackgroundTasks, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    if not biz.get("website"):
        raise HTTPException(400, "No website set")
    await db.knowledge_chunks.delete_many({"business_id": business_id, "source": {"$regex": "^http"}})
    invalidate(business_id)
    bg.add_task(_run_crawl, business_id, biz["website"])
    await db.businesses.update_one({"business_id": business_id}, {"$set": {"crawl_status": "crawling", "crawl_progress": 5}})
    return {"ok": True}


@router.post("/{business_id}/generate-snapshot")
async def generate_snapshot_now(business_id: str, bg: BackgroundTasks, user=Depends(get_current_user)):
    """Lets the owner (re)generate the AI's business overview on demand -- useful for
    manual-only businesses (no website) or after adding knowledge by hand."""
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    bg.add_task(_generate_snapshot, business_id)
    return {"ok": True, "message": "Generating snapshot in the background"}


# ---------------------------------------------------------------------------
# Appointment booking settings
# ---------------------------------------------------------------------------
@router.get("/{business_id}/appointments/settings")
async def get_appointment_settings(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz.get("appointment_settings") or DEFAULT_APPOINTMENT_SETTINGS


@router.put("/{business_id}/appointments/settings")
async def set_appointment_settings(business_id: str, payload: AppointmentSettingsIn, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    hours = {d: payload.working_hours.get(d) for d in valid_days}
    settings = {
        "enabled": payload.enabled,
        "services": [{"name": str(s.get("name", "")).strip()[:80],
                      "duration_minutes": max(5, min(480, int(s.get("duration_minutes", 30))))}
                     for s in payload.services if str(s.get("name", "")).strip()][:30],
        "working_hours": hours,
        "slot_interval_minutes": max(5, min(240, payload.slot_interval_minutes)),
    }
    await db.businesses.update_one({"business_id": business_id}, {"$set": {"appointment_settings": settings}})
    return settings


@router.get("/{business_id}/appointments")
async def list_appointments(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    items = await db.appointments.find(
        {"business_id": business_id, "status": "confirmed"}, {"_id": 0}
    ).sort("start_time", 1).to_list(500)
    return items


@router.post("/{business_id}/appointments/{appointment_id}/cancel")
async def owner_cancel_appointment(business_id: str, appointment_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    res = await db.appointments.update_one(
        {"id": appointment_id, "business_id": business_id}, {"$set": {"status": "cancelled"}}
    )
    if res.modified_count == 0:
        raise HTTPException(404, "Appointment not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Quick facts -- short, fast-to-edit fields that override/supplement crawled
# content for exactly the things that go stale fastest (hours, promos,
# temporary closures). Always injected into the chat prompt directly, never
# subject to retrieval ranking, and always treated as more current than
# crawled text -- see chat.py.
# ---------------------------------------------------------------------------
class QuickFactsIn(BaseModel):
    hours_note: str = Field(default="", max_length=300)
    special_or_promo: str = Field(default="", max_length=300)
    announcement: str = Field(default="", max_length=300)


@router.get("/{business_id}/quick-facts")
async def get_quick_facts(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    return biz.get("quick_facts") or DEFAULT_QUICK_FACTS


@router.put("/{business_id}/quick-facts")
async def set_quick_facts(business_id: str, payload: QuickFactsIn, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    facts = {**payload.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.businesses.update_one({"business_id": business_id}, {"$set": {"quick_facts": facts}})
    await touch_knowledge(business_id)
    return facts


# ---------------------------------------------------------------------------
# Inventory / stock feed -- CSV upload, stored as structured knowledge_chunks
# tagged source_type="inventory" so they flow through the exact same
# retrieval pipeline as crawled/manual knowledge (no parallel system to
# maintain). Re-uploading replaces the previous inventory entirely, so
# "upload the current file" is the whole update workflow for the owner.
# ---------------------------------------------------------------------------
import csv
import io


def _parse_inventory_csv(raw: bytes) -> list:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV appears to be empty")
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    name_col = next((cols[c] for c in ("name", "product", "item", "product_name", "title") if c in cols), None)
    if not name_col:
        raise HTTPException(400, "CSV needs a 'name' (or 'product'/'item'/'title') column")
    price_col = next((cols[c] for c in ("price", "cost", "amount") if c in cols), None)
    stock_col = next((cols[c] for c in ("stock", "stock_status", "availability", "quantity", "qty") if c in cols), None)
    desc_col = next((cols[c] for c in ("description", "details", "notes") if c in cols), None)

    items = []
    for row in reader:
        name = (row.get(name_col) or "").strip()
        if not name:
            continue
        items.append({
            "name": name[:200],
            "price": (row.get(price_col) or "").strip()[:100] if price_col else "",
            "stock": (row.get(stock_col) or "").strip()[:100] if stock_col else "",
            "description": (row.get(desc_col) or "").strip()[:500] if desc_col else "",
        })
        if len(items) >= 2000:  # sanity cap
            break
    if not items:
        raise HTTPException(400, "No usable rows found in that CSV")
    return items


@router.post("/{business_id}/inventory/upload")
async def upload_inventory(business_id: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    settings = await get_platform_settings()
    max_mb = int(settings.get("max_upload_mb", 15))
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {max_mb}MB)")
    items = _parse_inventory_csv(data)

    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for it in items:
        text = f"Product: {it['name']}"
        if it["price"]:
            text += f" | Price: {it['price']}"
        if it["stock"]:
            text += f" | Stock: {it['stock']}"
        if it["description"]:
            text += f" | {it['description']}"
        docs.append({
            "id": str(uuid.uuid4()),
            "business_id": business_id,
            "text": text,
            "source": file.filename,
            "source_title": f"Inventory: {it['name']}",
            "source_type": "inventory",
            "tokens": tokenize(text),
            "created_at": now,
        })

    # Replace previous inventory entirely -- re-uploading IS the update workflow.
    await db.knowledge_chunks.delete_many({"business_id": business_id, "source_type": "inventory"})
    await db.knowledge_chunks.insert_many(docs)
    invalidate(business_id)
    await touch_knowledge(business_id)
    return {"ok": True, "items_loaded": len(docs)}


@router.get("/{business_id}/inventory")
async def list_inventory(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Not found")
    items = await db.knowledge_chunks.find(
        {"business_id": business_id, "source_type": "inventory"}, {"_id": 0, "tokens": 0}
    ).sort("created_at", -1).to_list(2000)
    return items


@router.delete("/{business_id}/inventory")
async def clear_inventory(business_id: str, user=Depends(get_current_user)):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]})
    if not biz:
        raise HTTPException(404, "Not found")
    res = await db.knowledge_chunks.delete_many({"business_id": business_id, "source_type": "inventory"})
    invalidate(business_id)
    await touch_knowledge(business_id)
    return {"ok": True, "deleted": res.deleted_count}
