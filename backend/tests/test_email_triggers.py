def _create_business(client, **overrides):
    payload = {"name": "Email Wiring Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def _patch_email(monkeypatch, fn_name, sink):
    import email_sender

    async def fake(*args, **kwargs):
        sink.append((fn_name, args, kwargs))
        return True
    monkeypatch.setattr(email_sender, fn_name, fake)
    for mod_name in ("usage", "routers.chat", "routers.billing", "routers.auth"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
            if hasattr(mod, fn_name):
                monkeypatch.setattr(mod, fn_name, fake)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Quota alerts
# ---------------------------------------------------------------------------
def test_quota_alert_fires_once_at_75_percent(signed_up_owner, fake_db, monkeypatch):
    sent = []
    _patch_email(monkeypatch, "send_quota_alert_email", sent)

    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["monthly_used"] = 73  # one chat away from 74; the next takes it to exactly 75%
            b["monthly_limit"] = 100

    client.post("/api/auth/logout")
    client.post("/api/chat", json={"business_id": bid, "message": "hello"})  # -> 74, not yet
    assert not sent
    client.post("/api/chat", json={"business_id": bid, "message": "hello"})  # -> 75, crosses
    assert len(sent) == 1
    assert sent[0][1][3] == 75  # threshold positional arg

    client.post("/api/chat", json={"business_id": bid, "message": "hello"})  # -> 76, no re-fire
    assert len(sent) == 1


def test_quota_alert_resets_on_new_period(signed_up_owner, fake_db, monkeypatch):
    sent = []
    _patch_email(monkeypatch, "send_quota_alert_email", sent)

    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    for b in fake_db.businesses.docs:
        if b["business_id"] == bid:
            b["monthly_used"] = 100
            b["monthly_limit"] = 100
            b["quota_alerts_sent"] = [75, 90, 100]
            b["usage_period"] = "2020-01"  # force a rollover on the next request

    client.post("/api/auth/logout")
    client.post("/api/chat", json={"business_id": bid, "message": "hello"})

    b_after = next(b for b in fake_db.businesses.docs if b["business_id"] == bid)
    # rolled over to 0, then +1 for this chat = 1% -- no threshold crossed yet
    assert b_after["quota_alerts_sent"] == []
    assert not sent


# ---------------------------------------------------------------------------
# Referral reward idempotency (real bug found and fixed while wiring this email:
# the reward previously re-fired on every subsequent purchase, not just the first)
# ---------------------------------------------------------------------------
def test_referral_reward_fires_once_not_on_every_purchase(client, monkeypatch, fake_db):
    reward_sent = []
    _patch_email(monkeypatch, "send_referral_reward_email", reward_sent)

    client.post("/api/auth/signup", json={"email": "referrer@example.com", "password": "password123", "name": "Referrer"})
    referrer_code = client.get("/api/auth/me").json()["referral_code"]
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={
        "email": "referred@example.com", "password": "password123", "name": "Referred",
        "referral_code": referrer_code,
    })
    biz = _create_business(client)

    from tests.test_gst_billing import _purchase_plan
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)
    assert len(reward_sent) == 1

    # a second purchase (upgrade) by the same referred user must NOT re-trigger the reward
    _purchase_plan(client, biz["business_id"], "pro", monkeypatch)
    assert len(reward_sent) == 1

    referral = next(r for r in fake_db.referrals.docs if r["code"] == referrer_code)
    assert referral["status"] == "rewarded"


# ---------------------------------------------------------------------------
# Upgrade / cancellation confirmation emails
# ---------------------------------------------------------------------------
def test_upgrade_confirmation_email_sent_on_new_plan_purchase(signed_up_owner, monkeypatch):
    sent = []
    _patch_email(monkeypatch, "send_upgrade_confirmed_email", sent)

    client, _ = signed_up_owner
    biz = _create_business(client)
    from tests.test_gst_billing import _purchase_plan
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)
    assert len(sent) == 1


def test_cancellation_email_sent(signed_up_owner, monkeypatch):
    sent = []
    _patch_email(monkeypatch, "send_cancellation_confirmed_email", sent)

    client, _ = signed_up_owner
    biz = _create_business(client)
    from tests.test_gst_billing import _purchase_plan
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)

    client.post("/api/billing/cancel", json={"business_id": biz["business_id"], "immediate": True})
    assert len(sent) == 1
