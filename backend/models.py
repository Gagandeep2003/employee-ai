"""Reference schema for what's actually stored in each Mongo collection.

NOT used for runtime validation -- each router defines its own narrower Pydantic
input models for request bodies. This file exists purely as living documentation
of the document shape, kept in sync by hand when a router adds/changes a field.
"""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None
    role: str = "owner"  # owner | admin
    referral_code: str
    referred_by_code: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Business(BaseModel):
    model_config = ConfigDict(extra="ignore")
    business_id: str
    owner_user_id: str
    name: str
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    language: str = "en"
    timezone: str = "UTC"
    crawl_status: str = "pending"  # pending | crawling | done | error
    crawl_progress: int = 0
    knowledge_score: int = 0
    plan: str = "free"  # free | starter | pro
    monthly_limit: int = 100
    monthly_used: int = 0
    usage_period: str = ""  # "YYYY-MM" -- monthly_used rolls over when this no longer matches the current month (see usage.py)
    ai_snapshot: Optional[str] = None  # AI-generated overview of the business, shown during onboarding review
    ai_snapshot_generated_at: Optional[str] = None
    appointment_settings: Dict[str, Any] = Field(default_factory=lambda: {
        "enabled": False,
        "services": [],  # [{"name": str, "duration_minutes": int}]
        "working_hours": {d: None for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},  # [open,"HH:MM"]/[close,"HH:MM"] or None if closed
        "slot_interval_minutes": 30,
    })
    widget: Dict[str, Any] = Field(default_factory=lambda: {
        "primary_color": "#1E3F33",
        "accent_color": "#C4A47C",
        "welcome_message": "Hi there! I'm your AI Employee. How can I help you today?",
        "position": "bottom-right",
        "logo_url": None,
        "show_branding": True,
    })
    created_at: str = Field(default_factory=now_iso)


class KnowledgeChunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    business_id: str
    text: str
    source: str  # url | file:{name} | manual
    source_title: Optional[str] = None
    tokens: List[str] = []  # lowercase tokens for BM25
    created_at: str = Field(default_factory=now_iso)


class Conversation(BaseModel):
    conversation_id: str
    business_id: str
    visitor_id: str
    status: str = "open"  # open | escalated | closed
    unanswered: bool = False
    outcome: Optional[str] = None  # None | lead | booked | resolved | lost -- owner-tagged, or "booked" auto-set on a successful appointment
    created_at: str = Field(default_factory=now_iso)
    last_message_at: str = Field(default_factory=now_iso)
    message_count: int = 0


class Appointment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reference: str  # "APT-XXXXXX", shown to the customer for lookups/cancellation
    business_id: str
    service: str
    customer_name: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    start_time: str  # ISO 8601
    end_time: str
    status: str = "confirmed"  # confirmed | cancelled
    conversation_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class PaymentOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    razorpay_order_id: str
    business_id: str
    user_id: str
    plan: str
    amount_inr: int
    status: str = "created"  # created | paid | failed
    created_at: str = Field(default_factory=now_iso)


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:10]}")
    business_id: str
    user_id: str
    plan: str
    amount_inr: int
    status: str = "paid"  # paid | refunded
    provider: str = "razorpay"
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    business_id: str
    role: str  # user | assistant | system
    text: str
    confidence: Optional[float] = None
    created_at: str = Field(default_factory=now_iso)
