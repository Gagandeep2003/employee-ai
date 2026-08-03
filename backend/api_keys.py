"""Business API Keys -- scoped, expiring, rotatable secrets that let a business owner's
own systems call a small external REST surface (routers/public_api.py) without a browser
session. Same shown-once secret model as GitHub/Stripe: only a SHA-256 hash and a short
display prefix are ever stored.
"""
import uuid
import secrets as _secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import Header, HTTPException, Request

from db import db
from auth import hash_token
from platform_settings import get_settings
from ratelimit import api_key_rate_strategy
from limits import parse as parse_rate_limit

KEY_PREFIX = "aek_live_"

# Fixed vocabulary -- kept small and explicit rather than free-text so every scope maps to
# something the public API router actually checks. Extend this list and public_api.py
# together; a scope with no enforcing endpoint is a silent no-op that misleads whoever
# granted it.
AVAILABLE_SCOPES = [
    "business:read",
    "appointments:read",
    "appointments:write",
    "conversations:read",
    "analytics:read",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_key() -> str:
    return f"{KEY_PREFIX}{_secrets.token_urlsafe(32)}"


async def create_api_key(business_id: str, owner_user_id: str, name: str, scopes: List[str],
                          expires_in_days: Optional[int] = None, rate_limit_per_min: Optional[int] = None) -> tuple:
    invalid = [s for s in scopes if s not in AVAILABLE_SCOPES]
    if invalid:
        raise HTTPException(400, f"Unknown scope(s): {', '.join(invalid)}")
    if not scopes:
        raise HTTPException(400, "Select at least one scope")

    settings = await get_settings()
    raw_key = _generate_key()
    key_id = f"key_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": key_id,
        "business_id": business_id,
        "owner_user_id": owner_user_id,
        "name": name.strip()[:100] or "Untitled key",
        "key_prefix": raw_key[:len(KEY_PREFIX) + 8],
        "key_hash": hash_token(raw_key),
        "scopes": scopes,
        "status": "active",
        "rate_limit_per_min": int(rate_limit_per_min or settings.get("api_key_default_rate_limit_per_min", 60)),
        "request_count": 0,
        "created_at": _now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat() if expires_in_days else None,
        "last_used_at": None,
        "revoked_at": None,
        "rotated_from": None,
    }
    await db.api_keys.insert_one(doc)
    doc.pop("_id", None); doc.pop("key_hash", None)
    return doc, raw_key


async def list_api_keys(business_id: str) -> List[dict]:
    return await db.api_keys.find({"business_id": business_id}, {"_id": 0, "key_hash": 0}).sort("created_at", -1).to_list(200)


async def _get_owned_key(key_id: str, owner_user_id: str) -> dict:
    doc = await db.api_keys.find_one({"id": key_id, "owner_user_id": owner_user_id})
    if not doc:
        raise HTTPException(404, "API key not found")
    return doc


async def revoke_api_key(key_id: str, owner_user_id: str):
    doc = await _get_owned_key(key_id, owner_user_id)
    if doc["status"] == "revoked":
        return doc
    await db.api_keys.update_one({"id": key_id}, {"$set": {"status": "revoked", "revoked_at": _now_iso()}})
    return doc


async def rotate_api_key(key_id: str, owner_user_id: str) -> tuple:
    """Revokes the old secret and issues a brand new one with the same name/scopes/limits.
    The old key stops working immediately -- callers should switch to the new secret before
    rotating in production, same as any provider's key rotation."""
    old = await _get_owned_key(key_id, owner_user_id)
    await db.api_keys.update_one({"id": key_id}, {"$set": {"status": "revoked", "revoked_at": _now_iso()}})
    new_doc, raw_key = await create_api_key(
        old["business_id"], owner_user_id, old["name"], old["scopes"],
        rate_limit_per_min=old.get("rate_limit_per_min"),
    )
    await db.api_keys.update_one({"id": new_doc["id"]}, {"$set": {"rotated_from": key_id}})
    new_doc["rotated_from"] = key_id
    return new_doc, raw_key


async def key_usage(key_id: str, owner_user_id: str, limit: int = 100) -> dict:
    doc = await _get_owned_key(key_id, owner_user_id)
    recent = await db.api_key_usage.find({"key_id": key_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {
        "id": doc["id"], "name": doc["name"], "request_count": doc.get("request_count", 0),
        "last_used_at": doc.get("last_used_at"), "rate_limit_per_min": doc.get("rate_limit_per_min"),
        "recent_requests": recent,
    }


async def _record_usage(key_doc: dict, request: Request, status_code: int = 200):
    await db.api_keys.update_one({"id": key_doc["id"]}, {"$set": {"last_used_at": _now_iso()}, "$inc": {"request_count": 1}})
    await db.api_key_usage.insert_one({
        "id": str(uuid.uuid4()), "key_id": key_doc["id"], "business_id": key_doc["business_id"],
        "path": request.url.path, "method": request.method, "status_code": status_code,
        "created_at": _now_iso(),
    })


def require_api_key(required_scope: str):
    """FastAPI dependency factory. Usage: Depends(require_api_key("appointments:read")).
    Verifies the X-Api-Key header, checks it's active/unexpired/scoped correctly, enforces
    its configurable per-minute rate limit, records usage, and returns the key's document
    (route handlers read business_id off it -- an API key is scoped to exactly one business,
    it can never see or act on another business's data)."""
    async def dependency(request: Request, x_api_key: Optional[str] = Header(None, alias="X-Api-Key")) -> dict:
        if not x_api_key or not x_api_key.startswith(KEY_PREFIX):
            raise HTTPException(401, "Missing or malformed X-Api-Key header")
        key_hash = hash_token(x_api_key)
        doc = await db.api_keys.find_one({"key_hash": key_hash}, {"_id": 0})
        if not doc or doc["status"] != "active":
            raise HTTPException(401, "Invalid or revoked API key")
        if doc.get("expires_at") and doc["expires_at"] < _now_iso():
            raise HTTPException(401, "This API key has expired")
        if required_scope not in doc.get("scopes", []):
            raise HTTPException(403, f"This API key does not have the '{required_scope}' scope")

        limit = parse_rate_limit(f"{doc.get('rate_limit_per_min', 60)}/minute")
        if not api_key_rate_strategy.hit(limit, "apikey", doc["id"]):
            raise HTTPException(429, "Rate limit exceeded for this API key")

        await _record_usage(doc, request)
        return doc

    return dependency
