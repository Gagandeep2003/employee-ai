import hashlib
import hmac
import json
import uuid

import config


def _create_business(client, **overrides):
    payload = {"name": "GST Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def _login_admin(client, monkeypatch, email="gstadmin@example.com"):
    import auth as auth_module
    import asyncio
    monkeypatch.setattr(config, "ADMIN_EMAIL", email)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")
    asyncio.run(auth_module.seed_admin())
    client.post("/api/auth/login", json={"email": email, "password": "admin_password_123"})


# ---------------------------------------------------------------------------
# Fake Razorpay client -- real credentials aren't available in the test env
# ---------------------------------------------------------------------------
class _FakeOrder:
    def create(self, data):
        return {"id": f"order_fake_{uuid.uuid4().hex[:10]}", "amount": data["amount"], "currency": data["currency"]}


class _FakeUtility:
    fail = False

    def verify_payment_signature(self, params):
        if _FakeUtility.fail:
            raise Exception("signature mismatch")
        return True


class _FakePayment:
    refunds = []

    def refund(self, payment_id, data):
        r = {"id": f"rfnd_fake_{uuid.uuid4().hex[:8]}", "payment_id": payment_id, "amount": data["amount"]}
        _FakePayment.refunds.append(r)
        return r


class FakeRazorpayClient:
    def __init__(self):
        self.order = _FakeOrder()
        self.utility = _FakeUtility()
        self.payment = _FakePayment()


def _enable_razorpay(monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "fake_secret")
    monkeypatch.setattr(config, "RAZORPAY_ENABLED", True)
    monkeypatch.setattr(config, "RAZORPAY_WEBHOOK_SECRET", "webhook_secret_fake")
    import routers.billing as billing_router
    fake_client = FakeRazorpayClient()
    monkeypatch.setattr(billing_router, "_razorpay_client", lambda: fake_client)
    return fake_client


def _purchase_plan(client, business_id, plan, monkeypatch):
    """Full subscribe -> verify flow using the fake Razorpay client. Returns the response body of /verify."""
    _enable_razorpay(monkeypatch)
    r = client.post("/api/billing/subscribe", json={"business_id": business_id, "plan": plan})
    assert r.status_code == 200, r.text
    body = r.json()
    if not body.get("requires_payment"):
        return body
    order_id = body["order_id"]
    payment_id = f"pay_fake_{uuid.uuid4().hex[:8]}"
    r2 = client.post("/api/billing/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": "fake_sig",
    })
    assert r2.status_code == 200, r2.text
    return r2.json()


# ---------------------------------------------------------------------------
# GST details
# ---------------------------------------------------------------------------
def test_gst_details_roundtrip(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    r = client.put(f"/api/billing/gst-details/{bid}", json={
        "gst_state_code": "29", "gstin": "29AAAAA0000A1Z5",
        "billing_legal_name": "Sunrise Clinic Pvt Ltd", "billing_address": "Bangalore, Karnataka",
    })
    assert r.status_code == 200

    got = client.get(f"/api/billing/gst-details/{bid}").json()
    assert got["gst_state_code"] == "29"
    assert got["gstin"] == "29AAAAA0000A1Z5"
    assert "state_options" in got and len(got["state_options"]) > 10


def test_invalid_gstin_rejected(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.put(f"/api/billing/gst-details/{biz['business_id']}", json={"gstin": "not-a-real-gstin"})
    assert r.status_code == 400


def test_invalid_state_code_rejected(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.put(f"/api/billing/gst-details/{biz['business_id']}", json={"gst_state_code": "99999"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Purchase -> GST-compliant invoice
# ---------------------------------------------------------------------------
def test_paid_plan_purchase_generates_gst_invoice(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    client.put(f"/api/billing/gst-details/{bid}", json={"gst_state_code": "27"})  # same as seller default -> intra-state

    result = _purchase_plan(client, bid, "starter", monkeypatch)
    assert result["plan"] == "starter"

    invs = client.get(f"/api/billing/invoices/{bid}").json()
    assert len(invs) == 1
    inv = invs[0]
    assert inv["invoice_number"].startswith("INV-")
    assert inv["status"] == "paid"
    assert inv["is_intra_state"] is True
    assert inv["cgst_paise"] > 0 and inv["sgst_paise"] > 0 and inv["igst_paise"] == 0
    assert inv["cgst_paise"] + inv["sgst_paise"] == inv["total_tax_paise"]
    assert inv["taxable_value_paise"] + inv["total_tax_paise"] == inv["total_paise"]
    assert inv["total_paise"] == 99900  # unchanged checkout amount (GST-inclusive pricing)

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "starter"
    assert biz_after["subscription_status"] == "active"
    assert biz_after["current_period_end"]


def test_inter_state_purchase_uses_igst(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    client.put(f"/api/billing/gst-details/{bid}", json={"gst_state_code": "29"})  # different from seller default (27) -> inter-state

    _purchase_plan(client, bid, "starter", monkeypatch)
    inv = client.get(f"/api/billing/invoices/{bid}").json()[0]
    assert inv["is_intra_state"] is False
    assert inv["igst_paise"] > 0
    assert inv["cgst_paise"] == 0 and inv["sgst_paise"] == 0


def test_invoice_numbers_are_sequential(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz1 = _create_business(client, name="Biz One")
    _purchase_plan(client, biz1["business_id"], "starter", monkeypatch)
    biz2 = _create_business(client, name="Biz Two")
    _purchase_plan(client, biz2["business_id"], "starter", monkeypatch)

    n1 = client.get(f"/api/billing/invoices/{biz1['business_id']}").json()[0]["invoice_number"]
    n2 = client.get(f"/api/billing/invoices/{biz2['business_id']}").json()[0]["invoice_number"]
    seq1 = int(n1.rsplit("-", 1)[1])
    seq2 = int(n2.rsplit("-", 1)[1])
    assert seq2 == seq1 + 1


def test_invoice_pdf_downloadable(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)
    inv = client.get(f"/api/billing/invoices/{bid}").json()[0]

    r = client.get(f"/api/billing/invoices/{bid}/{inv['id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Proration & scheduled downgrades
# ---------------------------------------------------------------------------
def test_upgrade_mid_cycle_is_prorated(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    _enable_razorpay(monkeypatch)
    r = client.post("/api/billing/subscribe", json={"business_id": bid, "plan": "pro"})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_payment"] is True
    assert body["proration_applied"] is True
    # Full pro price is 2999*100=299900 paise; charge is just the prorated top-up, never
    # the full new price stacked on top of it (a real bug caught by this exact assertion).
    assert 0 < body["amount"] < 299900


def test_downgrade_scheduled_not_immediate(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "pro", monkeypatch)

    r = client.post("/api/billing/subscribe", json={"business_id": bid, "plan": "starter"})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_payment"] is False
    assert body["scheduled_plan_change"] == "starter"

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "pro"  # unchanged until period end
    assert biz_after["pending_plan_change"] == "starter"


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------
def test_cancel_immediate_downgrades_now(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    r = client.post("/api/billing/cancel", json={"business_id": bid, "immediate": True})
    assert r.status_code == 200
    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "free"
    assert biz_after["subscription_status"] == "canceled"


def test_cancel_at_period_end_keeps_access(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    r = client.post("/api/billing/cancel", json={"business_id": bid, "immediate": False})
    assert r.status_code == 200
    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "starter"  # still active
    assert biz_after["cancel_at_period_end"] is True


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
def test_admin_refund_full_amount(signed_up_owner, monkeypatch, fake_db):
    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)
    inv = client.get(f"/api/billing/invoices/{bid}").json()[0]

    _login_admin(client, monkeypatch)
    r = client.post("/api/billing/refund", json={"invoice_id": inv["id"]})
    assert r.status_code == 200
    assert r.json()["refunded_paise"] == inv["total_paise"]

    inv_after = next(i for i in fake_db.invoices.docs if i["id"] == inv["id"])
    assert inv_after["status"] == "refunded"
    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "free"  # full refund cancels the plan


def test_owner_cannot_issue_refund(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)
    inv = client.get(f"/api/billing/invoices/{biz['business_id']}").json()[0]

    r = client.post("/api/billing/refund", json={"invoice_id": inv["id"]})
    assert r.status_code == 403  # refunds are admin-only, not owner self-service


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
def _sign(body: bytes) -> str:
    return hmac.new(b"webhook_secret_fake", body, hashlib.sha256).hexdigest()


def test_webhook_payment_captured_activates_plan(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _enable_razorpay(monkeypatch)

    r = client.post("/api/billing/subscribe", json={"business_id": bid, "plan": "starter"})
    order_id = r.json()["order_id"]

    payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"order_id": order_id, "id": "pay_webhook_1"}}}}
    body = json.dumps(payload).encode()
    r2 = client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": _sign(body)})
    assert r2.status_code == 200

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "starter"


def test_webhook_rejects_bad_signature(client):
    body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    import routers.billing as billing_router
    original = config.RAZORPAY_WEBHOOK_SECRET
    config.RAZORPAY_WEBHOOK_SECRET = "webhook_secret_fake"
    try:
        r = client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": "wrong"})
        assert r.status_code == 400
    finally:
        config.RAZORPAY_WEBHOOK_SECRET = original


# ---------------------------------------------------------------------------
# Overage billing (off by default)
# ---------------------------------------------------------------------------
def test_overage_disabled_by_default_hard_blocks(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)
    await_none = fake_db.businesses.docs
    for b in await_none:
        if b["business_id"] == bid:
            b["monthly_used"] = b["monthly_limit"]

    client.post("/api/auth/logout")
    r = client.post("/api/chat", json={"business_id": bid, "message": "hello"})
    assert r.json().get("error") == "limit_reached"


def test_overage_enabled_allows_chat_and_tracks_count(signed_up_owner, monkeypatch, fake_db):
    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)
    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["monthly_used"] = b["monthly_limit"]

    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})
    _login_admin(client, monkeypatch)
    client.put("/api/admin/settings", json={"overage_billing_enabled": True})

    client.post("/api/auth/logout")
    r = client.post("/api/chat", json={"business_id": bid, "message": "hello"})
    assert r.status_code == 200
    assert "error" not in r.json()

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["overage_count"] == 1


# ---------------------------------------------------------------------------
# Billing lifecycle: renewal reminders, grace period, auto-downgrade
# ---------------------------------------------------------------------------
def test_renewal_reminder_sent_when_period_ending_soon(signed_up_owner, monkeypatch, fake_db):
    import asyncio
    from datetime import datetime, timezone, timedelta
    import scheduler

    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["current_period_end"] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    sent = {}
    async def fake_reminder(email, name, business_name, renews_by):
        sent["email"] = email
    import email_sender
    monkeypatch.setattr(email_sender, "send_renewal_reminder_email", fake_reminder)

    result = asyncio.run(scheduler.billing_lifecycle_job())
    assert result["reminded"] == 1
    assert sent.get("email") == owner["email"]


def test_expired_period_enters_grace_not_immediate_downgrade(signed_up_owner, monkeypatch, fake_db):
    import asyncio
    from datetime import datetime, timezone, timedelta
    import scheduler

    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["current_period_end"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    result = asyncio.run(scheduler.billing_lifecycle_job())
    assert result["entered_grace"] == 1

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "starter"  # still has access during grace
    assert biz_after["subscription_status"] == "past_due"
    assert biz_after["grace_period_ends_at"]


def test_grace_period_lapse_downgrades_to_free(signed_up_owner, monkeypatch, fake_db):
    import asyncio
    from datetime import datetime, timezone, timedelta
    import scheduler

    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)

    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["current_period_end"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            b["subscription_status"] = "past_due"
            b["grace_period_ends_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    result = asyncio.run(scheduler.billing_lifecycle_job())
    assert result["downgraded"] == 1

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "free"
    assert biz_after["subscription_status"] == "canceled"


def test_cancel_at_period_end_applies_on_expiry(signed_up_owner, monkeypatch, fake_db):
    import asyncio
    from datetime import datetime, timezone, timedelta
    import scheduler

    client, owner = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _purchase_plan(client, bid, "starter", monkeypatch)
    client.post("/api/billing/cancel", json={"business_id": bid, "immediate": False})

    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["current_period_end"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    result = asyncio.run(scheduler.billing_lifecycle_job())
    assert result["downgraded"] == 1

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    assert biz_after["plan"] == "free"
    assert biz_after["subscription_status"] == "canceled"
