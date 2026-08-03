import datetime
import pytest


# ---------------------------------------------------------------------------
# Refresh tokens & sessions
# ---------------------------------------------------------------------------
def test_login_sets_both_cookies(client):
    client.post("/api/auth/signup", json={"email": "s1@example.com", "password": "password123", "name": "S1"})
    assert "session_token" in client.cookies
    assert "refresh_token" in client.cookies


def test_refresh_rotates_tokens_and_keeps_session_valid(client):
    client.post("/api/auth/signup", json={"email": "s2@example.com", "password": "password123", "name": "S2"})
    old_refresh = client.cookies.get("refresh_token")

    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh and new_refresh != old_refresh

    # the rotated-in access token still works
    me = client.get("/api/auth/me")
    assert me.status_code == 200


def test_refresh_without_cookie_rejected(client):
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401


def test_reused_refresh_token_revokes_session(client):
    """Rotation-with-reuse-detection: replaying an already-rotated-away refresh
    token is treated as token theft and kills the session outright."""
    client.post("/api/auth/signup", json={"email": "s3@example.com", "password": "password123", "name": "S3"})
    old_refresh = client.cookies.get("refresh_token")

    r1 = client.post("/api/auth/refresh")
    assert r1.status_code == 200

    # replay the OLD (now-superseded) refresh token
    client.cookies.set("refresh_token", old_refresh)
    r2 = client.post("/api/auth/refresh")
    assert r2.status_code == 401

    # the session is now revoked entirely -- even the token issued by the
    # legitimate rotation in r1 no longer works
    r3 = client.post("/api/auth/refresh")
    assert r3.status_code == 401


def test_sessions_list_shows_current_device(signed_up_owner):
    client, _ = signed_up_owner
    r = client.get("/api/auth/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True
    assert "refresh_token_hash" not in sessions[0]


def test_second_device_appears_in_sessions_list(client):
    client.post("/api/auth/signup", json={"email": "multi@example.com", "password": "password123", "name": "M"})

    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as client2:
        client2.post("/api/auth/login", json={"email": "multi@example.com", "password": "password123"})
        sessions_from_2 = client2.get("/api/auth/sessions").json()
        assert len(sessions_from_2) == 2  # both devices visible from either one
        current_flags = [s["current"] for s in sessions_from_2]
        assert current_flags.count(True) == 1  # only this device is "current" from client2's perspective


def test_revoke_single_session(client):
    client.post("/api/auth/signup", json={"email": "revoke1@example.com", "password": "password123", "name": "R"})

    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as client2:
        client2.post("/api/auth/login", json={"email": "revoke1@example.com", "password": "password123"})
        other_session_id = [s for s in client2.get("/api/auth/sessions").json() if s["current"]][0]["id"]

        r = client.delete(f"/api/auth/sessions/{other_session_id}")
        assert r.status_code == 200
        assert r.json()["was_current_device"] is False

        # that device is now logged out
        assert client2.get("/api/auth/me").status_code == 401
        # this device (which did the revoking) is unaffected
        assert client.get("/api/auth/me").status_code == 200


def test_revoke_all_sessions_excludes_current_by_default(client):
    client.post("/api/auth/signup", json={"email": "revokeall@example.com", "password": "password123", "name": "R"})

    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as client2:
        client2.post("/api/auth/login", json={"email": "revokeall@example.com", "password": "password123"})

        r = client.post("/api/auth/sessions/revoke-all", json={"include_current": False})
        assert r.status_code == 200
        assert r.json()["revoked"] == 1

        assert client.get("/api/auth/me").status_code == 200      # this device: still in
        assert client2.get("/api/auth/me").status_code == 401     # other device: logged out


def test_logout_revokes_server_side_session(signed_up_owner, fake_db):
    client, user = signed_up_owner
    sessions_before = [s for s in fake_db.sessions.docs if s["user_id"] == user["user_id"] and s["revoked_at"] is None]
    assert len(sessions_before) == 1

    client.post("/api/auth/logout")
    sessions_after = [s for s in fake_db.sessions.docs if s["user_id"] == user["user_id"] and s["revoked_at"] is None]
    assert len(sessions_after) == 0


def test_password_reset_revokes_other_sessions(client, fake_db):
    client.post("/api/auth/signup", json={"email": "pwreset@example.com", "password": "originalpass1", "name": "P"})
    import auth as auth_module
    user = fake_db.users.docs[0]

    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as client2:
        client2.post("/api/auth/login", json={"email": "pwreset@example.com", "password": "originalpass1"})
        assert client2.get("/api/auth/me").status_code == 200

        token = auth_module.create_reset_token(user["user_id"])
        client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})

        assert client2.get("/api/auth/me").status_code == 401  # killed by the reset


# ---------------------------------------------------------------------------
# Login history & brute-force lockout
# ---------------------------------------------------------------------------
def test_login_history_records_success_and_failure(client):
    client.post("/api/auth/signup", json={"email": "hist@example.com", "password": "password123", "name": "H"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "hist@example.com", "password": "wrongpass"})
    client.post("/api/auth/login", json={"email": "hist@example.com", "password": "password123"})

    r = client.get("/api/auth/login-history")
    assert r.status_code == 200
    outcomes = [e["outcome"] for e in r.json()]
    assert outcomes.count("success") == 2   # signup + successful login
    assert outcomes.count("failed_password") == 1


def test_brute_force_lockout_after_max_attempts(client):
    client.post("/api/auth/signup", json={"email": "lockout@example.com", "password": "correctpass1", "name": "L"})
    client.post("/api/auth/logout")

    for _ in range(5):  # DEFAULTS["max_failed_login_attempts"]
        r = client.post("/api/auth/login", json={"email": "lockout@example.com", "password": "wrongpass"})
        assert r.status_code == 401

    # account is now locked -- even the CORRECT password is rejected until the cooldown passes
    r = client.post("/api/auth/login", json={"email": "lockout@example.com", "password": "correctpass1"})
    assert r.status_code == 423


def test_successful_login_clears_failed_attempt_counter(client, fake_db):
    client.post("/api/auth/signup", json={"email": "clear@example.com", "password": "correctpass1", "name": "C"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "clear@example.com", "password": "wrong"})
    client.post("/api/auth/login", json={"email": "clear@example.com", "password": "wrong"})
    r = client.post("/api/auth/login", json={"email": "clear@example.com", "password": "correctpass1"})
    assert r.status_code == 200
    user = next(u for u in fake_db.users.docs if u["email"] == "clear@example.com")
    assert user["failed_login_count"] == 0


# ---------------------------------------------------------------------------
# Security overview
# ---------------------------------------------------------------------------
def test_security_overview_reflects_state(signed_up_owner):
    client, _ = signed_up_owner
    r = client.get("/api/auth/security-overview")
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_enabled"] is False
    assert body["active_sessions"] == 1
    assert isinstance(body["checklist"], list)
    assert 0 <= body["score"] <= 100


# ---------------------------------------------------------------------------
# Business API Keys
# ---------------------------------------------------------------------------
def _create_business(client, **overrides):
    payload = {"name": "Test Clinic", "email": "clinic@example.com", "category": "Healthcare"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_api_key_returns_secret_once(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)

    r = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Zapier integration", "scopes": ["business:read"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["secret"].startswith("aek_live_")
    assert "key_hash" not in body

    listed = client.get(f"/api/api-keys?business_id={biz['business_id']}").json()
    assert len(listed) == 1
    assert "secret" not in listed[0]
    assert listed[0]["key_prefix"] in body["secret"]


def test_create_api_key_rejects_unknown_scope(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Bad", "scopes": ["delete:everything"],
    })
    assert r.status_code == 400


def test_api_key_cannot_be_created_for_someone_elses_business(client):
    client.post("/api/auth/signup", json={"email": "own1@example.com", "password": "password123", "name": "O1"})
    biz = _create_business(client)
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={"email": "own2@example.com", "password": "password123", "name": "O2"})
    r = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Sneaky", "scopes": ["business:read"],
    })
    assert r.status_code == 404


def test_public_api_requires_valid_key(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.get("/api/v1/business", headers={"X-Api-Key": "aek_live_not_a_real_key"})
    assert r.status_code == 401

    r_missing = client.get("/api/v1/business")
    assert r_missing.status_code == 401


def test_public_api_enforces_scope(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Read-only", "scopes": ["business:read"],
    }).json()

    ok = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    assert ok.status_code == 200
    assert ok.json()["business_id"] == biz["business_id"]

    forbidden = client.get("/api/v1/appointments", headers={"X-Api-Key": key["secret"]})
    assert forbidden.status_code == 403


def test_api_key_rotation_invalidates_old_secret(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Rotate me", "scopes": ["business:read"],
    }).json()

    rotated = client.post(f"/api/api-keys/{key['id']}/rotate")
    assert rotated.status_code == 200
    new_secret = rotated.json()["secret"]
    assert new_secret != key["secret"]

    old_still_works = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    assert old_still_works.status_code == 401
    new_works = client.get("/api/v1/business", headers={"X-Api-Key": new_secret})
    assert new_works.status_code == 200


def test_api_key_revocation(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Revoke me", "scopes": ["business:read"],
    }).json()

    r = client.delete(f"/api/api-keys/{key['id']}")
    assert r.status_code == 200

    denied = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    assert denied.status_code == 401


def test_api_key_rate_limit_enforced(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Tight limit", "scopes": ["business:read"], "rate_limit_per_min": 2,
    }).json()

    r1 = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    r2 = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    r3 = client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    assert [r1.status_code, r2.status_code] == [200, 200]
    assert r3.status_code == 429


def test_api_key_usage_tracked(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Tracked", "scopes": ["business:read"],
    }).json()
    client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})
    client.get("/api/v1/business", headers={"X-Api-Key": key["secret"]})

    usage = client.get(f"/api/api-keys/{key['id']}/usage")
    assert usage.status_code == 200
    assert usage.json()["request_count"] == 2
    assert len(usage.json()["recent_requests"]) == 2


def test_public_api_appointment_booking_scoped_to_business(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    fake_db.businesses.docs[0]["appointment_settings"] = {
        "enabled": True,
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "working_hours": {
            "mon": ["09:00", "12:00"], "tue": ["09:00", "12:00"], "wed": ["09:00", "12:00"],
            "thu": ["09:00", "12:00"], "fri": ["09:00", "12:00"], "sat": None, "sun": None,
        },
        "slot_interval_minutes": 30,
    }
    key = client.post("/api/api-keys", json={
        "business_id": biz["business_id"], "name": "Booking bot",
        "scopes": ["appointments:read", "appointments:write"],
    }).json()

    d = datetime.date.today() + datetime.timedelta(days=1)
    while d.weekday() != 0:  # next Monday
        d += datetime.timedelta(days=1)

    r = client.post("/api/v1/appointments", headers={"X-Api-Key": key["secret"]}, json={
        "service": "Consultation", "date": d.isoformat(), "time": "09:00",
        "customer_name": "Jordan", "customer_phone": "555-0100",
    })
    assert r.status_code == 200, r.text

    listed = client.get("/api/v1/appointments", headers={"X-Api-Key": key["secret"]})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
