def _create_business(client, **overrides):
    payload = {"name": "Landing Page Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def test_testimonials_roundtrip(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    r = client.put(f"/api/businesses/{bid}/testimonials", json={"testimonials": [
        {"quote": "Best service in town!", "author": "Priya S.", "role": "Regular customer"},
        {"quote": "Quick and professional.", "author": "Amit K."},
    ]})
    assert r.status_code == 200
    assert len(r.json()) == 2

    got = client.get(f"/api/businesses/{bid}/testimonials").json()
    assert got[0]["author"] == "Priya S."
    assert got[1]["role"] is None


def test_testimonials_empty_by_default_no_fabricated_content(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    assert client.get(f"/api/businesses/{biz['business_id']}/testimonials").json() == []


def test_landing_page_data_public_no_auth_required(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client, category="Healthcare", phone="555-0100")
    bid = biz["business_id"]
    client.put(f"/api/businesses/{bid}/quick-facts", json={"hours_note": "Open every day"})
    client.put(f"/api/businesses/{bid}/testimonials", json={"testimonials": [
        {"quote": "Great!", "author": "Jamie"},
    ]})

    client.post("/api/auth/logout")
    r = client.get(f"/api/chat/business/{bid}/landing-page")
    assert r.status_code == 200
    body = r.json()
    assert body["business_name"] == "Landing Page Biz"
    assert body["category"] == "Healthcare"
    assert body["quick_facts"]["hours_note"] == "Open every day"
    assert body["testimonials"][0]["author"] == "Jamie"
    assert body["appointment_settings"]["enabled"] is False


def test_landing_page_includes_faqs_from_both_creation_paths(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    client.post("/api/knowledge/manual", json={
        "business_id": bid, "title": "Do you offer refunds?", "kind": "faq",
        "text": "Yes, within 30 days of purchase.",
    })

    r = client.get(f"/api/chat/business/{bid}/landing-page")
    faqs = r.json()["faqs"]
    assert len(faqs) == 1
    assert faqs[0]["question"] == "Do you offer refunds?"
    assert "30 days" in faqs[0]["answer"]


def test_landing_page_404_for_unknown_business(client):
    r = client.get("/api/chat/business/nonexistent_biz/landing-page")
    assert r.status_code == 404
