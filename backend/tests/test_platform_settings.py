def _create_business(client, **overrides):
    payload = {"name": "Settings Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def _login_admin(client, fake_db, monkeypatch):
    import auth as auth_module
    import config
    import asyncio
    monkeypatch.setattr(config, "ADMIN_EMAIL", "settingsadmin@example.com")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")
    asyncio.run(auth_module.seed_admin())
    client.post("/api/auth/login", json={"email": "settingsadmin@example.com", "password": "admin_password_123"})


def test_maintenance_mode_blocks_public_chat(signed_up_owner, fake_db, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    client.post("/api/auth/logout")

    _login_admin(client, fake_db, monkeypatch)
    r = client.put("/api/admin/settings", json={"maintenance_mode": True})
    assert r.status_code == 200
    client.post("/api/auth/logout")

    chat_r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "hello"})
    assert chat_r.status_code == 200
    assert chat_r.json().get("error") == "maintenance"


def test_admin_can_tune_free_plan_limit_and_new_businesses_use_it(signed_up_owner, fake_db, monkeypatch):
    client, _ = signed_up_owner
    _login_admin(client, fake_db, monkeypatch)
    r = client.put("/api/admin/settings", json={"default_free_limit": 5})
    assert r.status_code == 200
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={"email": "tunedlimit@example.com", "password": "password123", "name": "T"})
    biz = _create_business(client)
    assert biz["monthly_limit"] == 5


def test_billing_plans_reflects_admin_tuned_limit(signed_up_owner, fake_db, monkeypatch):
    client, _ = signed_up_owner
    _login_admin(client, fake_db, monkeypatch)
    client.put("/api/admin/settings", json={"starter_limit": 12345})
    client.post("/api/auth/logout")

    r = client.get("/api/billing/plans")
    assert r.status_code == 200
    assert r.json()["starter"]["limit"] == 12345


def test_upload_size_limit_is_configurable(signed_up_owner, fake_db, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    client.post("/api/auth/logout")
    _login_admin(client, fake_db, monkeypatch)
    client.put("/api/admin/settings", json={"max_upload_mb": 1})
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"email": signed_up_owner[1]["email"], "password": "supersecret1"})
    big_file = b"x" * (2 * 1024 * 1024)  # 2MB, over the 1MB limit just set
    r = client.post(
        "/api/knowledge/upload",
        data={"business_id": biz["business_id"]},
        files={"file": ("big.txt", big_file, "text/plain")},
    )
    assert r.status_code == 400
    assert "1MB" in r.json()["detail"]
