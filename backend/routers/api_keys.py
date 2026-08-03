from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional

from auth import get_current_user
from db import db
from audit import log as audit_log
from ratelimit import limiter
import api_keys as api_keys_lib

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


async def _verify_ownership(business_id: str, user: dict):
    biz = await db.businesses.find_one({"business_id": business_id, "owner_user_id": user["user_id"]}, {"_id": 0})
    if not biz:
        raise HTTPException(404, "Business not found")
    return biz


@router.get("/scopes")
async def scopes():
    return {"scopes": api_keys_lib.AVAILABLE_SCOPES}


class CreateKeyInput(BaseModel):
    business_id: str
    name: str = Field(min_length=1, max_length=100)
    scopes: List[str]
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=730)
    rate_limit_per_min: Optional[int] = Field(default=None, ge=1, le=6000)


@router.post("")
@limiter.limit("20/hour")
async def create_key(request: Request, payload: CreateKeyInput, user=Depends(get_current_user)):
    await _verify_ownership(payload.business_id, user)
    doc, raw_key = await api_keys_lib.create_api_key(
        payload.business_id, user["user_id"], payload.name, payload.scopes,
        payload.expires_in_days, payload.rate_limit_per_min,
    )
    await audit_log(request, user["user_id"], "api_key.created", "api_key", doc["id"],
                     {"name": doc["name"], "scopes": doc["scopes"], "business_id": payload.business_id})
    # The raw secret is returned exactly once -- it is never retrievable again after this response.
    return {**doc, "secret": raw_key}


@router.get("")
async def list_keys(business_id: str, user=Depends(get_current_user)):
    await _verify_ownership(business_id, user)
    return await api_keys_lib.list_api_keys(business_id)


@router.post("/{key_id}/rotate")
@limiter.limit("20/hour")
async def rotate_key(request: Request, key_id: str, user=Depends(get_current_user)):
    doc, raw_key = await api_keys_lib.rotate_api_key(key_id, user["user_id"])
    await audit_log(request, user["user_id"], "api_key.rotated", "api_key", doc["id"], {"rotated_from": key_id})
    return {**doc, "secret": raw_key}


@router.delete("/{key_id}")
async def revoke_key(request: Request, key_id: str, user=Depends(get_current_user)):
    doc = await api_keys_lib.revoke_api_key(key_id, user["user_id"])
    await audit_log(request, user["user_id"], "api_key.revoked", "api_key", key_id, {"name": doc.get("name")})
    return {"ok": True}


@router.get("/{key_id}/usage")
async def usage(key_id: str, user=Depends(get_current_user)):
    return await api_keys_lib.key_usage(key_id, user["user_id"])
