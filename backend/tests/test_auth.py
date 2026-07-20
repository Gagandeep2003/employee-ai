def test_signup_creates_account_and_sets_cookie(client):
    r = client.post("/api/auth/signup", json={
        "email": "alice@example.com", "password": "password123", "name": "Alice",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert "session_token" in r.cookies
    # the raw JWT must never be handed back in the response body (XSS/localStorage risk)
    assert "token" not in body


def test_signup_duplicate_email_rejected(client):
    payload = {"email": "bob@example.com", "password": "password123", "name": "Bob"}
    r1 = client.post("/api/auth/signup", json=payload)
    assert r1.status_code == 200
    r2 = client.post("/api/auth/signup", json=payload)
    assert r2.status_code == 400


def test_signup_short_password_rejected(client):
    r = client.post("/api/auth/signup", json={
        "email": "short@example.com", "password": "123", "name": "Short",
    })
    assert r.status_code == 422  # pydantic min_length=8


def test_login_wrong_password_rejected(client):
    client.post("/api/auth/signup", json={
        "email": "carol@example.com", "password": "password123", "name": "Carol",
    })
    r = client.post("/api/auth/login", json={"email": "carol@example.com", "password": "wrongpass"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_returns_current_user(signed_up_owner):
    client, user = signed_up_owner
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == user["email"]


def test_logout_clears_session(signed_up_owner):
    client, _ = signed_up_owner
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 401


def test_signup_starts_unverified(client):
    r = client.post("/api/auth/signup", json={
        "email": "unverified@example.com", "password": "password123", "name": "U",
    })
    assert r.status_code == 200
    assert r.json()["email_verified"] is False


def test_password_reset_flow(client, fake_db):
    client.post("/api/auth/signup", json={
        "email": "reset@example.com", "password": "originalpass1", "name": "R",
    })
    import auth as auth_module
    user = fake_db.users.docs[0]
    token = auth_module.create_reset_token(user["user_id"])

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
    assert r.status_code == 200

    # old password no longer works, new one does
    client.post("/api/auth/logout")
    r_old = client.post("/api/auth/login", json={"email": "reset@example.com", "password": "originalpass1"})
    assert r_old.status_code == 401
    r_new = client.post("/api/auth/login", json={"email": "reset@example.com", "password": "brandnewpass1"})
    assert r_new.status_code == 200


def test_password_reset_rejects_wrong_token_type(client, fake_db):
    client.post("/api/auth/signup", json={
        "email": "wrongtype@example.com", "password": "originalpass1", "name": "W",
    })
    import auth as auth_module
    user = fake_db.users.docs[0]
    # an access (session) token must NOT work as a password-reset token
    access_token = auth_module.create_token(user["user_id"], user["email"])
    r = client.post("/api/auth/reset-password", json={"token": access_token, "new_password": "irrelevant1"})
    assert r.status_code == 400


def test_forgot_password_does_not_leak_whether_email_exists(client):
    r1 = client.post("/api/auth/forgot-password", json={"email": "doesnotexist@example.com"})
    r2 = client.post("/api/auth/forgot-password", json={"email": "doesnotexist@example.com"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()


def test_email_verification_flow(signed_up_owner, fake_db):
    client, user = signed_up_owner
    import auth as auth_module
    full = fake_db.users.docs[0]
    token = auth_module.create_verify_token(full["user_id"])

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200

    me = client.get("/api/auth/me").json()
    assert me["email_verified"] is True


def test_resend_verification_requires_auth(client):
    r = client.post("/api/auth/verify-email/resend")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Admin MFA
# ---------------------------------------------------------------------------
def _make_admin(client, fake_db, monkeypatch):
    import auth as auth_module
    import config
    import asyncio
    monkeypatch.setattr(config, "ADMIN_EMAIL", "admin2@example.com")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")
    asyncio.run(auth_module.seed_admin())
    client.post("/api/auth/login", json={"email": "admin2@example.com", "password": "admin_password_123"})


def test_mfa_setup_requires_admin(signed_up_owner):
    client, _ = signed_up_owner
    r = client.post("/api/admin/mfa/setup")
    assert r.status_code == 403


def test_mfa_full_enable_login_disable_cycle(client, fake_db, monkeypatch):
    import pyotp
    _make_admin(client, fake_db, monkeypatch)

    setup = client.post("/api/admin/mfa/setup")
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    bad_code = client.post("/api/admin/mfa/enable", json={"code": "000000"})
    assert bad_code.status_code == 401

    good_code = pyotp.TOTP(secret).now()
    enable = client.post("/api/admin/mfa/enable", json={"code": good_code})
    assert enable.status_code == 200

    # Now log out and log back in -- should require the second factor
    client.post("/api/auth/logout")
    login = client.post("/api/auth/login", json={"email": "admin2@example.com", "password": "admin_password_123"})
    assert login.status_code == 200
    assert login.json().get("mfa_required") is True
    mfa_token = login.json()["mfa_token"]

    # Session must not be usable yet
    me_before = client.get("/api/auth/me")
    assert me_before.status_code == 401

    verify = client.post("/api/auth/mfa/verify", json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200

    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 200

    disable_wrong = client.post("/api/admin/mfa/disable", json={"password": "not-the-password"})
    assert disable_wrong.status_code == 401
    disable_ok = client.post("/api/admin/mfa/disable", json={"password": "admin_password_123"})
    assert disable_ok.status_code == 200


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------
def test_google_login_disabled_by_default(client):
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code == 503


def test_google_callback_disabled_by_default(client):
    r = client.get("/api/auth/google/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code == 503


def test_google_login_redirects_when_configured(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback")
    monkeypatch.setattr(config, "GOOGLE_OAUTH_ENABLED", True)

    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "accounts.google.com" in r.headers["location"]
    assert "oauth_state" in r.cookies


def test_google_callback_rejects_state_mismatch(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback")
    monkeypatch.setattr(config, "GOOGLE_OAUTH_ENABLED", True)

    client.cookies.set("oauth_state", "correct-state")
    r = client.get("/api/auth/google/callback?code=abc&state=wrong-state", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "error=oauth_state_mismatch" in r.headers["location"]


def test_find_or_create_google_user_links_existing_account(client, fake_db):
    client.post("/api/auth/signup", json={"email": "linkme@example.com", "password": "password123", "name": "Link Me"})
    assert fake_db.users.docs[0].get("google_id") is None

    import auth as auth_module
    import asyncio
    linked = asyncio.run(auth_module.find_or_create_google_user(
        email="linkme@example.com", name="Link Me", picture="http://pic.example/x.jpg", google_id="google-123",
    ))
    assert linked["user_id"] == fake_db.users.docs[0]["user_id"]
    assert fake_db.users.docs[0]["google_id"] == "google-123"
    assert fake_db.users.docs[0]["email_verified"] is True  # Google verified it, even though ours wasn't yet
