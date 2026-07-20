def _create_business(client, **overrides):
    payload = {"name": "Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def test_plans_endpoint_public(client):
    r = client.get("/api/billing/plans")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"free", "starter", "pro"}
    assert body["free"]["price_inr"] == 0


def test_free_plan_subscribe_requires_no_payment(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post("/api/billing/subscribe", json={"business_id": biz["business_id"], "plan": "free"})
    assert r.status_code == 200
    assert r.json()["requires_payment"] is False


def test_paid_plan_subscribe_without_razorpay_configured_fails_cleanly(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post("/api/billing/subscribe", json={"business_id": biz["business_id"], "plan": "starter"})
    # RAZORPAY_KEY_ID/SECRET aren't set in the test env -- should be a clean 503, not a crash
    assert r.status_code == 503


def test_subscribe_invalid_plan_rejected(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post("/api/billing/subscribe", json={"business_id": biz["business_id"], "plan": "enterprise"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Admin guard: the core security fix -- no implicit "first user is admin"
# ---------------------------------------------------------------------------
def test_regular_owner_cannot_access_admin(signed_up_owner):
    client, _ = signed_up_owner
    r = client.get("/api/admin/overview")
    assert r.status_code == 403


def test_first_signed_up_user_is_not_auto_admin(client):
    """This is the actual vulnerability that was fixed: previously the first user
    ever created became an implicit admin. Now role must be explicitly 'admin'."""
    client.post("/api/auth/signup", json={"email": "first@example.com", "password": "password123", "name": "First"})
    r = client.get("/api/admin/overview")
    assert r.status_code == 403


def test_seeded_admin_can_access_admin_overview(client, fake_db, monkeypatch):
    import auth as auth_module
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin_password_123")
    import config
    monkeypatch.setattr(config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")

    import asyncio
    asyncio.run(auth_module.seed_admin())

    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin_password_123"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    r2 = client.get("/api/admin/overview")
    assert r2.status_code == 200
