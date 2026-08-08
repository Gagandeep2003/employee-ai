"""
Notification System API
Handles in-app notifications, broadcasts, and user notification management
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid

from db import db
from auth import get_current_user
from services.job_queue import get_job_queue, send_notification_job

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationCreate(BaseModel):
    """Admin creates notification for users"""
    user_id: Optional[str] = None  # null for broadcast
    business_id: Optional[str] = None
    target_group: Optional[str] = None  # all | free | paid | specific_business
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=1000)
    type: str = "info"  # info | warning | announcement | system


class NotificationResponse(BaseModel):
    notification_id: str
    user_id: Optional[str]
    business_id: Optional[str]
    target_group: Optional[str]
    title: str
    message: str
    type: str
    read: bool
    read_at: Optional[str]
    created_by: Optional[str]
    created_at: str


@router.post("/broadcast", response_model=Dict[str, Any])
async def broadcast_notification(request: Request, payload: NotificationCreate, current_user: dict = Depends(get_current_user)):
    """
    Admin broadcasts notification to users
    - target_group: 'all', 'free', 'paid', or 'specific_business'
    - If business_id provided, sends to that business only
    - Uses background job queue for non-blocking delivery
    """
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    
    # Validate target group
    valid_groups = ["all", "free", "paid", "specific_business"]
    if payload.target_group and payload.target_group not in valid_groups:
        raise HTTPException(400, f"Invalid target_group. Must be one of: {valid_groups}")
    
    # Determine recipients
    recipients = []
    
    if payload.business_id:
        # Send to specific business owner
        biz = await db.businesses.find_one({"business_id": payload.business_id})
        if not biz:
            raise HTTPException(404, "Business not found")
        recipients.append(biz["owner_user_id"])
    
    elif payload.target_group == "all":
        # Get all users
        async for user in db.users.find({}, {"user_id": 1}):
            recipients.append(user["user_id"])
    
    elif payload.target_group == "free":
        # Get all free plan users
        async for biz in db.businesses.find({"plan": "free"}, {"owner_user_id": 1}):
            if biz["owner_user_id"] not in recipients:
                recipients.append(biz["owner_user_id"])
    
    elif payload.target_group == "paid":
        # Get all paid plan users
        async for biz in db.businesses.find({"plan": {"$in": ["starter", "pro", "growth", "scale"]}}, {"owner_user_id": 1}):
            if biz["owner_user_id"] not in recipients:
                recipients.append(biz["owner_user_id"])
    
    # Create notification records
    notification_ids = []
    now = datetime.now(timezone.utc).isoformat()
    
    for recipient_id in recipients:
        notification_id = f"ntf_{uuid.uuid4().hex[:12]}"
        notification_doc = {
            "notification_id": notification_id,
            "user_id": recipient_id,
            "business_id": payload.business_id,
            "target_group": payload.target_group,
            "title": payload.title,
            "message": payload.message,
            "type": payload.type,
            "read": False,
            "read_at": None,
            "created_by": current_user["user_id"],
            "created_at": now
        }
        await db.notifications.insert_one(notification_doc)
        notification_ids.append(notification_id)
        
        # Queue background job for email notification (optional)
        # job_queue.enqueue(send_notification_job, recipient_id, payload.title, payload.message)
    
    return {
        "success": True,
        "notification_id": notification_ids[0] if len(notification_ids) == 1 else notification_ids,
        "recipients_count": len(recipients),
        "message": f"Notification sent to {len(recipients)} users"
    }


@router.get("", response_model=List[NotificationResponse])
async def get_user_notifications(current_user: dict = Depends(get_current_user)):
    """Get all notifications for current user"""
    user_id = current_user["user_id"]
    
    # Get notifications addressed to this user or broadcasts
    notifications = await db.notifications.find(
        {
            "$or": [
                {"user_id": user_id},
                {"target_group": "all"}
            ]
        },
        {"_id": 0}
    ).sort("created_at", -1).limit(100).to_list(100)
    
    return notifications


@router.get("/unread-count", response_model=Dict[str, int])
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    """Get count of unread notifications"""
    user_id = current_user["user_id"]
    
    count = await db.notifications.count_documents(
        {
            "$or": [
                {"user_id": user_id},
                {"target_group": "all"}
            ],
            "read": False
        }
    )
    
    return {"unread_count": count}


@router.post("/{notification_id}/read", response_model=Dict[str, Any])
async def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a notification as read"""
    user_id = current_user["user_id"]
    
    result = await db.notifications.update_one(
        {
            "notification_id": notification_id,
            "$or": [
                {"user_id": user_id},
                {"target_group": "all"}
            ]
        },
        {
            "$set": {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    
    return {"success": True, "message": "Notification marked as read"}


@router.post("/mark-all-read", response_model=Dict[str, Any])
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """Mark all user notifications as read"""
    user_id = current_user["user_id"]
    
    result = await db.notifications.update_many(
        {
            "$or": [
                {"user_id": user_id},
                {"target_group": "all"}
            ],
            "read": False
        },
        {
            "$set": {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"success": True, "marked_count": result.modified_count}


@router.delete("/{notification_id}", response_model=Dict[str, Any])
async def delete_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a notification"""
    user_id = current_user["user_id"]
    
    result = await db.notifications.delete_one({
        "notification_id": notification_id,
        "user_id": user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(404, "Notification not found")
    
    return {"success": True, "message": "Notification deleted"}
