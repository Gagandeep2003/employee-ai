"""Support tickets router for owners to submit and track support requests."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from auth import get_current_user
from db import db
from audit import log as audit_log
from models import SupportTicket
from email_service import send_notification_email

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketCreateIn(BaseModel):
    subject: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    priority: str = "medium"  # low | medium | high | critical
    category: str = "general"  # general | technical | billing | feature_request


class TicketUpdateIn(BaseModel):
    admin_response: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = None  # open | in_progress | resolved | closed


class TicketResponse(BaseModel):
    ticket_id: str
    business_id: str
    owner_user_id: str
    subject: str
    description: str
    priority: str
    status: str
    category: str
    admin_response: Optional[str]
    resolved_at: Optional[str]
    created_at: str
    updated_at: str


@router.post("", response_model=dict)
async def create_ticket(payload: TicketCreateIn, request: Request, user=Depends(get_current_user)):
    """Create a new support ticket (owner only)."""
    if user.get("role") != "owner":
        raise HTTPException(403, "Only business owners can create tickets")
    
    # Get user's business
    business = await db.businesses.find_one({"owner_user_id": user["user_id"]})
    if not business:
        raise HTTPException(404, "No business found for this user")
    
    now = datetime.now(timezone.utc).isoformat()
    ticket = {
        "ticket_id": f"tkt_{uuid.uuid4().hex[:12]}",
        "business_id": business["business_id"],
        "owner_user_id": user["user_id"],
        "subject": payload.subject,
        "description": payload.description,
        "priority": payload.priority,
        "status": "open",
        "category": payload.category,
        "admin_response": None,
        "resolved_at": None,
        "created_at": now,
        "updated_at": now,
    }
    
    await db.tickets.insert_one(ticket)
    await audit_log(request, user["user_id"], "ticket.created", "ticket", ticket["ticket_id"], {
        "subject": payload.subject,
        "category": payload.category,
        "priority": payload.priority
    })
    
    # Notify admins about new ticket (optional email)
    admins = await db.users.find({"role": "admin"}).to_list(length=None)
    for admin in admins:
        # Could send email notification here
        pass
    
    return {"ok": True, "ticket_id": ticket["ticket_id"]}


@router.get("", response_model=List[TicketResponse])
async def list_tickets(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List tickets for the current user's business (owner) or all tickets (admin)."""
    query = {}
    
    if user.get("role") == "owner":
        business = await db.businesses.find_one({"owner_user_id": user["user_id"]})
        if not business:
            return []
        query["business_id"] = business["business_id"]
    elif user.get("role") != "admin":
        raise HTTPException(403, "Access denied")
    
    if status:
        query["status"] = status
    
    tickets = await db.tickets.find(query)\
        .sort("created_at", -1)\
        .skip(skip)\
        .limit(limit)\
        .to_list(length=limit)
    
    return [TicketResponse(**t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, user=Depends(get_current_user)):
    """Get a specific ticket by ID."""
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    # Authorization check
    if user.get("role") == "owner":
        business = await db.businesses.find_one({"owner_user_id": user["user_id"]})
        if not business or ticket["business_id"] != business["business_id"]:
            raise HTTPException(404, "Ticket not found")
    elif user.get("role") != "admin":
        raise HTTPException(403, "Access denied")
    
    return TicketResponse(**ticket)


@router.patch("/{ticket_id}", response_model=dict)
async def update_ticket(ticket_id: str, payload: TicketUpdateIn, request: Request, 
                        user=Depends(get_current_user)):
    """Update a ticket (admin only for status/response, owner can add info)."""
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}
    
    if user.get("role") == "admin":
        # Admin can update status and add response
        if payload.status is not None:
            update_data["status"] = payload.status
            if payload.status == "resolved":
                update_data["resolved_at"] = now
        if payload.admin_response is not None:
            update_data["admin_response"] = payload.admin_response
        
        await db.tickets.update_one({"ticket_id": ticket_id}, {"$set": update_data})
        await audit_log(request, user["user_id"], "ticket.updated", "ticket", ticket_id, {
            "status": payload.status,
            "has_response": payload.admin_response is not None
        })
        
        # Notify owner about update
        owner = await db.users.find_one({"user_id": ticket["owner_user_id"]})
        if owner and owner.get("email"):
            await send_notification_email(
                owner["email"],
                f"Ticket Update: {ticket['subject']}",
                f"Your support ticket has been updated.\n\nStatus: {update_data.get('status', ticket['status'])}\n\n" +
                (f"Admin Response:\n{payload.admin_response}\n\n" if payload.admin_response else "") +
                "Log in to your dashboard to view the full details."
            )
    
    elif user.get("role") == "owner":
        # Owner can only add additional information if ticket is not closed
        if ticket["status"] == "closed":
            raise HTTPException(400, "Cannot update a closed ticket")
        
        business = await db.businesses.find_one({"owner_user_id": user["user_id"]})
        if not business or ticket["business_id"] != business["business_id"]:
            raise HTTPException(404, "Ticket not found")
        
        # For now, owners can't directly update via this endpoint
        # They should create a new ticket referencing this one if needed
        raise HTTPException(403, "Owners cannot update tickets. Please create a new ticket if you have additional information.")
    
    else:
        raise HTTPException(403, "Access denied")
    
    return {"ok": True}


@router.delete("/{ticket_id}", response_model=dict)
async def delete_ticket(ticket_id: str, request: Request, user=Depends(get_current_user)):
    """Delete a ticket (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Only admins can delete tickets")
    
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    await db.tickets.delete_one({"ticket_id": ticket_id})
    await audit_log(request, user["user_id"], "ticket.deleted", "ticket", ticket_id, {})
    
    return {"ok": True}
