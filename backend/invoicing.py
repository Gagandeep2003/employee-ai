"""GST-compliant sequential invoice numbering + invoice creation orchestration.

GST law requires invoice numbers to be sequential and unique within a financial year
(April-March in India), with no gaps. This uses an atomic counter document per financial
year (db.counters) so concurrent invoice creation can never produce a duplicate or skipped
number, and generates a real invoice PDF for every paid transaction.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

from db import db
import gst
from platform_settings import get_settings
from invoice_pdf import render_invoice_pdf
from storage import put_object

logger = logging.getLogger("roviq-ai.invoicing")


def _financial_year(dt: datetime) -> str:
    """India's financial year runs Apr 1 -> Mar 31; Jan-Mar belongs to the FY that started
    the previous April."""
    start_year = dt.year if dt.month >= 4 else dt.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


async def next_invoice_number(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    fy = _financial_year(dt)
    counter = await db.counters.find_one_and_update(
        {"id": f"invoice_{fy}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
    )
    return f"INV-{fy}-{counter['seq']:06d}"


async def create_invoice(business_id: str, user_id: str, plan: str, amount_paise: int, *,
                         description: str, razorpay_order_id: Optional[str] = None,
                         razorpay_payment_id: Optional[str] = None, status: str = "paid") -> dict:
    """The single place an invoice record gets created -- computes GST, assigns a
    compliant sequential number, generates and stores the PDF, and inserts the document.
    `amount_paise` is the GST-inclusive amount (this platform's plan prices are advertised
    and charged as GST-inclusive) -- negative produces a credit note (refunds, downgrade
    credits). `status="due"` (used for overage invoices) records a real, numbered GST
    invoice without implying it's been collected -- this app has no stored payment method /
    auto-charge capability, so a due invoice is collected at the business's next plan
    purchase (see routers/billing.py's subscribe()) rather than charged automatically.
    Used for plan purchases, overage billing, and proration charges."""
    settings = await get_settings()
    biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0})
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})

    gst_rate = float(settings.get("gst_rate", 18.0)) if settings.get("gst_enabled", True) else 0.0
    sign = -1 if amount_paise < 0 else 1
    gst_calc = gst.compute_gst_inclusive(
        abs(amount_paise),
        buyer_state_code=(biz or {}).get("gst_state_code"),
        seller_state_code=settings.get("seller_state_code", "27"),
        gst_rate=gst_rate,
    )
    if sign < 0:  # credit note: mirror every money field negative (is_intra_state/gst_rate untouched)
        for money_key in ("taxable_value_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_tax_paise", "total_paise"):
            gst_calc[money_key] = -gst_calc[money_key]

    number = await next_invoice_number()
    now = datetime.now(timezone.utc).isoformat()
    is_credit_note = amount_paise < 0

    invoice = {
        "id": f"inv_{uuid.uuid4().hex[:10]}",
        "invoice_number": number,
        "document_type": "credit_note" if is_credit_note else "tax_invoice",
        "business_id": business_id,
        "user_id": user_id,
        "plan": plan,
        "description": description,
        "status": "paid" if is_credit_note else status,
        "provider": "razorpay",
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "refund_amount_paise": 0,
        "refunded_at": None,
        "hsn_sac_code": settings.get("hsn_sac_code", "998314"),
        "seller_snapshot": {
            "legal_name": settings.get("seller_legal_name", ""),
            "gstin": settings.get("seller_gstin", ""),
            "state_code": settings.get("seller_state_code", "27"),
            "address": settings.get("seller_address", ""),
        },
        "buyer_snapshot": {
            "legal_name": (biz or {}).get("billing_legal_name") or (biz or {}).get("name", ""),
            "gstin": (biz or {}).get("gstin", ""),
            "state_code": (biz or {}).get("gst_state_code", ""),
            "address": (biz or {}).get("billing_address", ""),
            "email": (user or {}).get("email", ""),
        },
        **gst_calc,
        "amount_inr": round(gst_calc["total_paise"] / 100),  # kept for older UI reading this field directly
        "pdf_path": None,
        "created_at": now,
    }

    try:
        pdf_bytes = render_invoice_pdf(invoice)
        pdf_path = f"invoices/{business_id}/{number}.pdf"
        put_object(pdf_path, pdf_bytes, "application/pdf")
        invoice["pdf_path"] = pdf_path
    except Exception as e:
        # A PDF failure must never block the invoice record -- the numbers/amounts are the
        # compliance-critical part. The PDF can be regenerated on demand (see
        # routers/billing.py's pdf endpoint, which renders on the fly if pdf_path is unset).
        logger.warning("Invoice PDF generation failed for %s: %s", number, e)

    await db.invoices.insert_one(invoice)
    invoice.pop("_id", None)
    return invoice
