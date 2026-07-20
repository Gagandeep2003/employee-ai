def _create_business(client, **overrides):
    payload = {"name": "Test Clinic", "email": "clinic@example.com", "category": "Healthcare"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_business_without_website_skips_crawl(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    assert biz["crawl_status"] == "done"
    assert biz["plan"] == "free"
    assert biz["monthly_limit"] == 100
    assert biz["appointment_settings"]["enabled"] is False


def test_business_list_and_get_scoped_to_owner(client):
    client.post("/api/auth/signup", json={"email": "u1@example.com", "password": "password123", "name": "U1"})
    biz = _create_business(client)
    r = client.get("/api/businesses")
    assert r.status_code == 200
    assert any(b["business_id"] == biz["business_id"] for b in r.json())

    r2 = client.get(f"/api/businesses/{biz['business_id']}")
    assert r2.status_code == 200


def test_other_owner_cannot_see_business(client):
    client.post("/api/auth/signup", json={"email": "owner1@example.com", "password": "password123", "name": "O1"})
    biz = _create_business(client)
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={"email": "owner2@example.com", "password": "password123", "name": "O2"})
    r = client.get(f"/api/businesses/{biz['business_id']}")
    assert r.status_code == 404  # tenant isolation: not visible to a different owner


def test_update_business(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.patch(f"/api/businesses/{biz['business_id']}", json={"name": "Renamed Clinic"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed Clinic"


def test_manual_knowledge_add_list_edit_delete(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    r = client.post("/api/knowledge/manual", json={
        "business_id": bid, "title": "Pricing", "text": "A checkup costs 500 rupees.",
    })
    assert r.status_code == 200, r.text

    r2 = client.get(f"/api/knowledge/{bid}/chunks")
    assert r2.status_code == 200
    chunks = r2.json()
    assert len(chunks) == 1
    chunk_id = chunks[0]["id"]

    r3 = client.patch(f"/api/knowledge/chunks/{chunk_id}", json={"text": "A checkup costs 600 rupees now."})
    assert r3.status_code == 200

    r4 = client.get(f"/api/knowledge/{bid}/chunks")
    assert "600" in r4.json()[0]["text"]

    r5 = client.delete(f"/api/knowledge/chunks/{chunk_id}")
    assert r5.status_code == 200
    r6 = client.get(f"/api/knowledge/{bid}/chunks")
    assert len(r6.json()) == 0


def test_knowledge_cannot_be_edited_by_other_owner(client):
    client.post("/api/auth/signup", json={"email": "kowner1@example.com", "password": "password123", "name": "K1"})
    biz = _create_business(client)
    client.post("/api/knowledge/manual", json={"business_id": biz["business_id"], "title": "T", "text": "Secret pricing info."})
    chunk_id = client.get(f"/api/knowledge/{biz['business_id']}/chunks").json()[0]["id"]
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={"email": "kowner2@example.com", "password": "password123", "name": "K2"})
    r = client.delete(f"/api/knowledge/chunks/{chunk_id}")
    assert r.status_code in (403, 404)


def test_appointment_settings_roundtrip(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    settings = {
        "enabled": True,
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "working_hours": {"mon": ["09:00", "17:00"], "tue": ["09:00", "17:00"], "wed": None,
                          "thu": None, "fri": None, "sat": None, "sun": None},
        "slot_interval_minutes": 30,
    }
    r = client.put(f"/api/businesses/{bid}/appointments/settings", json=settings)
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    r2 = client.get(f"/api/businesses/{bid}/appointments/settings")
    assert r2.status_code == 200
    assert r2.json()["services"][0]["name"] == "Consultation"


def test_generate_snapshot_endpoint(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post(f"/api/businesses/{biz['business_id']}/generate-snapshot")
    assert r.status_code == 200
