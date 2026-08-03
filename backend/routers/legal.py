"""Legal CMS: admin-managed legal documents (Privacy Policy, Terms of Service, etc.) with
versioning and a publish/draft workflow, plus acceptance tracking for the documents that
require it.

Every save creates a new, immutable version rather than overwriting the last one -- that's
the whole point of versioning a legal document: you need to be able to point to exactly
what a user agreed to on a given date, even after the document has since changed. Only one
version per doc_type is "published" (live/public) at a time; drafts are saved and previewed
freely without affecting what's currently live.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from db import db
from audit import log as audit_log

router = APIRouter(prefix="/legal", tags=["legal"])

DOC_TYPES = {
    "privacy_policy": "Privacy Policy",
    "terms_of_service": "Terms of Service",
    "refund_policy": "Refund Policy",
    "cookie_policy": "Cookie Policy",
    "acceptable_use_policy": "Acceptable Use Policy",
    "security_policy": "Security Policy",
    "gdpr": "GDPR Compliance Statement",
    "dpa": "Data Processing Agreement",
}

# Documents a user must actively accept -- at signup, and again if a newer version is
# published after they last accepted.
ACCEPTANCE_REQUIRED = {"terms_of_service", "privacy_policy"}


async def _ensure_admin(user: dict):
    from routers.admin import _ensure_admin as check_admin
    await check_admin(user)


def _require_valid_type(doc_type: str):
    if doc_type not in DOC_TYPES:
        raise HTTPException(404, f"Unknown document type '{doc_type}'. Valid types: {', '.join(DOC_TYPES)}")


@router.get("/document-types")
async def document_types():
    return {"types": DOC_TYPES, "acceptance_required": sorted(ACCEPTANCE_REQUIRED)}


@router.get("/{doc_type}")
async def get_published(doc_type: str):
    """Public -- the current live version of a legal document. 404 if nothing's been
    published for this type yet (a fresh deployment before the admin has written any)."""
    _require_valid_type(doc_type)
    doc = await db.legal_documents.find_one(
        {"doc_type": doc_type, "is_published": True}, {"_id": 0}, sort=[("version", -1)],
    )
    if not doc:
        raise HTTPException(404, "This document hasn't been published yet")
    return doc


@router.get("/admin/{doc_type}/versions")
async def list_versions(doc_type: str, user=Depends(get_current_user)):
    await _ensure_admin(user)
    _require_valid_type(doc_type)
    return await db.legal_documents.find(
        {"doc_type": doc_type}, {"_id": 0, "content": 0},
    ).sort("version", -1).to_list(200)


@router.get("/admin/{doc_type}/versions/{version}")
async def get_version(doc_type: str, version: int, user=Depends(get_current_user)):
    await _ensure_admin(user)
    doc = await db.legal_documents.find_one({"doc_type": doc_type, "version": version}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Version not found")
    return doc


class SaveDraftIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200000)


@router.post("/admin/{doc_type}/draft")
async def save_draft(doc_type: str, payload: SaveDraftIn, request: Request, user=Depends(get_current_user)):
    """Saves a new draft version -- does NOT affect what's currently published. Publish it
    explicitly (POST .../publish) when it's ready to go live."""
    await _ensure_admin(user)
    _require_valid_type(doc_type)
    last = await db.legal_documents.find_one({"doc_type": doc_type}, {"_id": 0, "version": 1}, sort=[("version", -1)])
    version = (last["version"] + 1) if last else 1
    doc = {
        "id": f"legal_{uuid.uuid4().hex[:10]}",
        "doc_type": doc_type,
        "title": payload.title.strip(),
        "content": payload.content,
        "version": version,
        "is_published": False,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "published_at": None,
    }
    await db.legal_documents.insert_one(doc)
    await audit_log(request, user["user_id"], "legal.draft_saved", "legal_document", doc["id"],
                    {"doc_type": doc_type, "version": version})
    doc.pop("_id", None)
    return doc


@router.post("/admin/{doc_type}/versions/{version}/publish")
async def publish_version(doc_type: str, version: int, request: Request, user=Depends(get_current_user)):
    """Makes this version the live/public one. Un-publishes whatever was live before --
    exactly one version is published per doc_type at any time."""
    await _ensure_admin(user)
    _require_valid_type(doc_type)
    doc = await db.legal_documents.find_one({"doc_type": doc_type, "version": version})
    if not doc:
        raise HTTPException(404, "Version not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.legal_documents.update_many({"doc_type": doc_type, "is_published": True},
                                        {"$set": {"is_published": False}})
    await db.legal_documents.update_one({"doc_type": doc_type, "version": version},
                                        {"$set": {"is_published": True, "published_at": now}})
    await audit_log(request, user["user_id"], "legal.published", "legal_document", doc["id"],
                    {"doc_type": doc_type, "version": version})
    return {"ok": True, "doc_type": doc_type, "version": version, "published_at": now}


# ---------------------------------------------------------------------------
# Acceptance tracking (Terms of Service / Privacy Policy)
# ---------------------------------------------------------------------------
@router.get("/acceptance/status")
async def acceptance_status(user=Depends(get_current_user)):
    """Which required documents (if any) the current user needs to (re-)accept -- either
    they've never accepted one, or a newer version has been published since they last did."""
    full_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "legal_acceptances": 1})
    accepted = (full_user or {}).get("legal_acceptances") or {}  # {doc_type: version}
    outstanding = []
    for doc_type in ACCEPTANCE_REQUIRED:
        current = await db.legal_documents.find_one(
            {"doc_type": doc_type, "is_published": True}, {"_id": 0, "version": 1, "title": 1},
        )
        if not current:
            continue  # nothing published for this type yet -- nothing to require acceptance of
        if accepted.get(doc_type) != current["version"]:
            outstanding.append({"doc_type": doc_type, "title": current["title"], "version": current["version"]})
    return {"outstanding": outstanding}


class AcceptIn(BaseModel):
    doc_type: str
    version: int


@router.post("/acceptance/accept")
async def accept(payload: AcceptIn, request: Request, user=Depends(get_current_user)):
    if payload.doc_type not in ACCEPTANCE_REQUIRED:
        raise HTTPException(400, f"'{payload.doc_type}' doesn't require acceptance")
    doc = await db.legal_documents.find_one({"doc_type": payload.doc_type, "version": payload.version, "is_published": True})
    if not doc:
        raise HTTPException(404, "That version isn't the currently published one -- refresh and try again")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {f"legal_acceptances.{payload.doc_type}": payload.version,
                  f"legal_acceptance_dates.{payload.doc_type}": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}
