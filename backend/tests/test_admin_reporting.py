import asyncio


def _login_admin(client, monkeypatch, email="reportadmin@example.com"):
    import config
    import auth as auth_module
    monkeypatch.setattr(config, "ADMIN_EMAIL", email)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")
    asyncio.run(auth_module.seed_admin())
    client.post("/api/auth/login", json={"email": email, "password": "admin_password_123"})


def _create_business(client, **overrides):
    payload = {"name": "Report Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


# ---------------------------------------------------------------------------
# Export formats
# ---------------------------------------------------------------------------
def test_businesses_export_csv(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _create_business(client)
    _login_admin(client, monkeypatch)

    r = client.get("/api/admin/businesses", params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "Report Test Biz" in r.text
    assert "Health Score" in r.text  # header row present


def test_businesses_export_xlsx(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _create_business(client)
    _login_admin(client, monkeypatch)

    r = client.get("/api/admin/businesses", params={"format": "xlsx"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r.content[:2] == b"PK"  # xlsx is a zip container


def test_businesses_export_pdf(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _create_business(client)
    _login_admin(client, monkeypatch)

    r = client.get("/api/admin/businesses", params={"format": "pdf"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_invalid_export_format_rejected(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _login_admin(client, monkeypatch)
    r = client.get("/api/admin/businesses", params={"format": "docx"})
    assert r.status_code == 400


def test_invoices_export(signed_up_owner, monkeypatch):
    client, owner = signed_up_owner
    biz = _create_business(client)
    from tests.test_gst_billing import _purchase_plan
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)

    _login_admin(client, monkeypatch)
    r = client.get("/api/admin/invoices", params={"format": "csv"})
    assert r.status_code == 200
    assert "INV-" in r.text


def test_owner_cannot_access_admin_reports(signed_up_owner):
    client, _ = signed_up_owner
    assert client.get("/api/admin/businesses").status_code == 403
    assert client.get("/api/admin/growth").status_code == 403
    assert client.get("/api/admin/churn").status_code == 403


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------
def test_health_score_present_and_bounded(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _create_business(client)
    _login_admin(client, monkeypatch)

    items = client.get("/api/admin/businesses").json()
    assert len(items) >= 1
    for b in items:
        assert 0 <= b["health"] <= 100


# ---------------------------------------------------------------------------
# Growth & churn
# ---------------------------------------------------------------------------
def test_growth_report_shape(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _create_business(client)
    _login_admin(client, monkeypatch)

    rows = client.get("/api/admin/growth", params={"months": 3}).json()
    assert len(rows) == 3
    assert all("new_signups" in r and "month" in r for r in rows)
    # the current month should include the business just created
    assert rows[-1]["new_signups"] >= 1


def test_churn_report_reflects_real_cancellation(signed_up_owner, monkeypatch, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    from tests.test_gst_billing import _purchase_plan
    _purchase_plan(client, biz["business_id"], "starter", monkeypatch)
    client.post("/api/billing/cancel", json={"business_id": biz["business_id"], "immediate": True})

    biz_after = next(b for b in fake_db.businesses.docs if b["business_id"] == biz["business_id"])
    assert biz_after.get("canceled_at")  # the underlying data churn is computed from

    _login_admin(client, monkeypatch)
    rows = client.get("/api/admin/churn", params={"months": 2}).json()
    assert rows[-1]["canceled"] >= 1
