import asyncio


def _login_admin(client, monkeypatch, email="legaladmin@example.com"):
    import config
    import auth as auth_module
    monkeypatch.setattr(config, "ADMIN_EMAIL", email)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "admin_password_123")
    asyncio.run(auth_module.seed_admin())
    client.post("/api/auth/login", json={"email": email, "password": "admin_password_123"})


def test_unknown_doc_type_rejected(client):
    r = client.get("/api/legal/not_a_real_type")
    assert r.status_code == 404


def test_unpublished_document_404s_publicly(client):
    r = client.get("/api/legal/privacy_policy")
    assert r.status_code == 404


def test_owner_cannot_manage_legal_docs(signed_up_owner):
    client, _ = signed_up_owner
    r = client.post("/api/legal/admin/privacy_policy/draft", json={"title": "Privacy Policy", "content": "We respect your privacy."})
    assert r.status_code == 403


def test_draft_then_publish_workflow(client, monkeypatch):
    _login_admin(client, monkeypatch)

    r1 = client.post("/api/legal/admin/terms_of_service/draft", json={"title": "Terms of Service", "content": "v1 content"})
    assert r1.status_code == 200
    assert r1.json()["version"] == 1
    assert r1.json()["is_published"] is False

    # not live yet
    assert client.get("/api/legal/terms_of_service").status_code == 404

    r2 = client.post("/api/legal/admin/terms_of_service/versions/1/publish")
    assert r2.status_code == 200

    live = client.get("/api/legal/terms_of_service").json()
    assert live["content"] == "v1 content"
    assert live["is_published"] is True


def test_new_version_supersedes_previous_published(client, monkeypatch):
    _login_admin(client, monkeypatch)
    client.post("/api/legal/admin/cookie_policy/draft", json={"title": "Cookie Policy", "content": "v1"})
    client.post("/api/legal/admin/cookie_policy/versions/1/publish")
    client.post("/api/legal/admin/cookie_policy/draft", json={"title": "Cookie Policy", "content": "v2"})
    client.post("/api/legal/admin/cookie_policy/versions/2/publish")

    live = client.get("/api/legal/cookie_policy").json()
    assert live["content"] == "v2"
    assert live["version"] == 2

    versions = client.get("/api/legal/admin/cookie_policy/versions").json()
    assert len(versions) == 2
    published_flags = {v["version"]: v["is_published"] for v in versions}
    assert published_flags == {1: False, 2: True}  # only the latest published version stays live


def test_version_history_preserves_old_content(client, monkeypatch):
    _login_admin(client, monkeypatch)
    client.post("/api/legal/admin/dpa/draft", json={"title": "DPA", "content": "original wording"})
    client.post("/api/legal/admin/dpa/versions/1/publish")
    client.post("/api/legal/admin/dpa/draft", json={"title": "DPA", "content": "revised wording"})
    client.post("/api/legal/admin/dpa/versions/2/publish")

    v1 = client.get("/api/legal/admin/dpa/versions/1").json()
    assert v1["content"] == "original wording"


# ---------------------------------------------------------------------------
# Acceptance tracking
# ---------------------------------------------------------------------------
def test_acceptance_required_when_never_accepted(signed_up_owner, client, monkeypatch):
    _login_admin(client, monkeypatch)
    client.post("/api/legal/admin/terms_of_service/draft", json={"title": "ToS", "content": "..."})
    client.post("/api/legal/admin/terms_of_service/versions/1/publish")

    owner_client, _ = signed_up_owner
    status = owner_client.get("/api/legal/acceptance/status").json()
    assert any(o["doc_type"] == "terms_of_service" for o in status["outstanding"])


def test_accepting_clears_outstanding_status(signed_up_owner, client, monkeypatch):
    _login_admin(client, monkeypatch)
    client.post("/api/legal/admin/privacy_policy/draft", json={"title": "Privacy", "content": "..."})
    client.post("/api/legal/admin/privacy_policy/versions/1/publish")

    owner_client, _ = signed_up_owner
    r = owner_client.post("/api/legal/acceptance/accept", json={"doc_type": "privacy_policy", "version": 1})
    assert r.status_code == 200

    status = owner_client.get("/api/legal/acceptance/status").json()
    assert not any(o["doc_type"] == "privacy_policy" for o in status["outstanding"])


def test_new_version_requires_reacceptance(signed_up_owner, client, monkeypatch):
    _login_admin(client, monkeypatch)
    client.post("/api/legal/admin/terms_of_service/draft", json={"title": "ToS", "content": "v1"})
    client.post("/api/legal/admin/terms_of_service/versions/1/publish")

    owner_client, _ = signed_up_owner
    owner_client.post("/api/legal/acceptance/accept", json={"doc_type": "terms_of_service", "version": 1})
    assert not owner_client.get("/api/legal/acceptance/status").json()["outstanding"]

    # a new version is published -- the old acceptance no longer covers it
    client.post("/api/legal/admin/terms_of_service/draft", json={"title": "ToS", "content": "v2, updated clauses"})
    client.post("/api/legal/admin/terms_of_service/versions/2/publish")

    status = owner_client.get("/api/legal/acceptance/status").json()
    assert any(o["doc_type"] == "terms_of_service" and o["version"] == 2 for o in status["outstanding"])
