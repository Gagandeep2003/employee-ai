from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
import uuid, io
from datetime import datetime, timezone

from auth import get_current_user
from db import db
from storage import put_object, APP_NAME
from retrieval import tokenize, invalidate
from platform_settings import get_settings as get_platform_settings
from freshness import touch as touch_knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class ManualEntry(BaseModel):
    business_id: str
    title: str
    text: str


async def _verify_ownership(business_id: str, user: dict):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    return biz


def _chunk_text(text: str, size: int = 700, overlap: int = 80) -> List[str]:
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        c = " ".join(words[i:i + size])
        if len(c.strip()) > 40:
            out.append(c)
        i += size - overlap
    return out


def _extract_bytes(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if lower.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if lower.endswith(".txt") or lower.endswith(".md") or lower.endswith(".csv"):
        return data.decode("utf-8", errors="ignore")
    raise HTTPException(400, "Unsupported file type. Use PDF, DOCX, TXT, MD, or CSV.")


@router.post("/manual")
async def add_manual(payload: ManualEntry, user=Depends(get_current_user)):
    await _verify_ownership(payload.business_id, user)
    chunks = _chunk_text(payload.text)
    docs = []
    for c in chunks:
        docs.append({
            "id": str(uuid.uuid4()),
            "business_id": payload.business_id,
            "text": c,
            "source": "manual",
            "source_title": payload.title,
            "tokens": tokenize(c),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    if docs:
        await db.knowledge_chunks.insert_many(docs)
    invalidate(payload.business_id)
    await touch_knowledge(payload.business_id)
    return {"added": len(docs)}


@router.post("/upload")
async def upload_file(business_id: str = Form(...), file: UploadFile = File(...), user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    data = await file.read()
    settings = await get_platform_settings()
    max_mb = int(settings.get("max_upload_mb", 15))
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {max_mb}MB)")
    text = _extract_bytes(file.filename, data)
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/{business_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, file.content_type or "application/octet-stream")
    except Exception as e:
        # Continue even if storage fails; we still index the text
        result = {"path": path, "size": len(data)}
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id,
        "business_id": business_id,
        "storage_path": result.get("path", path),
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    chunks = _chunk_text(text)
    docs = []
    for c in chunks:
        docs.append({
            "id": str(uuid.uuid4()),
            "business_id": business_id,
            "text": c,
            "source": f"file:{file_id}",
            "source_title": file.filename,
            "tokens": tokenize(c),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    if docs:
        await db.knowledge_chunks.insert_many(docs)
    invalidate(business_id)
    await touch_knowledge(business_id)
    return {"file_id": file_id, "chunks": len(docs), "filename": file.filename}


@router.get("/{business_id}/chunks")
async def list_chunks(business_id: str, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    items = await db.knowledge_chunks.find({"business_id": business_id}, {"_id": 0, "tokens": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/{business_id}/files")
async def list_files(business_id: str, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    items = await db.files.find({"business_id": business_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str, user=Depends(get_current_user)):
    doc = await db.knowledge_chunks.find_one({"id": chunk_id})
    if not doc:
        raise HTTPException(404, "Not found")
    await _verify_ownership(doc["business_id"], user)
    await db.knowledge_chunks.delete_one({"id": chunk_id})
    invalidate(doc["business_id"])
    await touch_knowledge(doc["business_id"])
    return {"ok": True}


class ChunkEdit(BaseModel):
    text: str


@router.patch("/chunks/{chunk_id}")
async def edit_chunk(chunk_id: str, payload: ChunkEdit, user=Depends(get_current_user)):
    """Lets the owner correct something the AI learned during onboarding review,
    instead of only being able to delete it."""
    doc = await db.knowledge_chunks.find_one({"id": chunk_id})
    if not doc:
        raise HTTPException(404, "Not found")
    await _verify_ownership(doc["business_id"], user)
    text = payload.text.strip()
    if len(text) < 5:
        raise HTTPException(400, "Text too short")
    await db.knowledge_chunks.update_one({"id": chunk_id}, {"$set": {"text": text, "tokens": tokenize(text)}})
    invalidate(doc["business_id"])
    await touch_knowledge(doc["business_id"])
    return {"ok": True}


@router.get("/{business_id}/score")
async def score(business_id: str, user=Depends(get_current_user)):
    biz = await _verify_ownership(business_id, user)
    count = await db.knowledge_chunks.count_documents({"business_id": business_id})
    missing = []
    text_all = " ".join([d["text"] async for d in db.knowledge_chunks.find({"business_id": business_id}, {"text": 1, "_id": 0}).limit(200)]).lower()
    checks = {
        "pricing": ["price", "pricing", "cost", "$", "rupee", "inr", "usd"],
        "hours": ["hour", "open", "close", "monday", "am", "pm"],
        "contact": ["email", "phone", "contact", "@"],
        "location": ["address", "located", "street", "avenue", "city"],
        "faq": ["faq", "question", "frequently"],
        "policy": ["refund", "return", "policy", "terms"],
    }
    for k, keys in checks.items():
        if not any(kw in text_all for kw in keys):
            missing.append(k)
    return {"chunks": count, "score": biz.get("knowledge_score", 0), "missing": missing, "crawl_status": biz.get("crawl_status")}
