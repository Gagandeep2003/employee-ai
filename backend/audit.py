"""Audit logging helper — record every important admin/business action.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request

from db import db


async def log(request: Optional[Request], actor_user_id: Optional[str], action: str,
              target_type: str = "", target_id: str = "", details: Optional[dict] = None):
    ip = None
    if request is not None:
        ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "actor_user_id": actor_user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "ip": ip,
        "details": details or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
