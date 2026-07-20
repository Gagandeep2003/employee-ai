import io


def _create_business(client, **overrides):
    payload = {"name": "Freshness Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def test_quick_facts_roundtrip(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    r = client.get(f"/api/businesses/{bid}/quick-facts")
    assert r.status_code == 200
    assert r.json()["hours_note"] == ""

    r2 = client.put(f"/api/businesses/{bid}/quick-facts", json={
        "hours_note": "Open till 9pm today", "special_or_promo": "20% off", "announcement": "",
    })
    assert r2.status_code == 200
    assert r2.json()["hours_note"] == "Open till 9pm today"
    assert r2.json()["updated_at"] is not None

    r3 = client.get(f"/api/businesses/{bid}/quick-facts")
    assert r3.json()["special_or_promo"] == "20% off"


def test_quick_facts_update_touches_knowledge_freshness(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    original_touch = biz["knowledge_last_updated_at"]

    client.put(f"/api/businesses/{biz['business_id']}/quick-facts", json={
        "hours_note": "New hours", "special_or_promo": "", "announcement": "",
    })
    updated = fake_db.businesses.docs[0]
    assert updated["knowledge_last_updated_at"] >= original_touch


def test_quick_facts_injected_into_chat_prompt(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    client.put(f"/api/businesses/{biz['business_id']}/quick-facts", json={
        "hours_note": "Open till midnight tonight only", "special_or_promo": "", "announcement": "",
    })
    client.post("/api/auth/logout")

    import routers.chat as chat_router
    captured = {}

    async def fake_rag_answer(business_name, business_context, history, question, **kw):
        captured.update(kw)
        return "ok"
    monkeypatch.setattr(chat_router, "rag_answer", fake_rag_answer)

    client.post("/api/chat", json={"business_id": biz["business_id"], "message": "what are your hours"})
    assert "midnight" in captured.get("live_info", "")


def test_inventory_csv_upload_and_list(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    csv_content = b"name,price,stock\nBlue Shirt,999,In Stock\nRed Hat,499,Out of Stock\n"

    r = client.post(
        f"/api/businesses/{biz['business_id']}/inventory/upload",
        files={"file": ("products.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items_loaded"] == 2

    r2 = client.get(f"/api/businesses/{biz['business_id']}/inventory")
    assert r2.status_code == 200
    items = r2.json()
    assert len(items) == 2
    assert any("Blue Shirt" in i["text"] and "999" in i["text"] for i in items)


def test_inventory_reupload_replaces_previous(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    client.post(f"/api/businesses/{bid}/inventory/upload",
               files={"file": ("v1.csv", io.BytesIO(b"name,price\nOld Item,10\n"), "text/csv")})
    client.post(f"/api/businesses/{bid}/inventory/upload",
               files={"file": ("v2.csv", io.BytesIO(b"name,price\nNew Item,20\n"), "text/csv")})

    items = client.get(f"/api/businesses/{bid}/inventory").json()
    assert len(items) == 1
    assert "New Item" in items[0]["text"]


def test_inventory_upload_rejects_csv_without_name_column(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.post(
        f"/api/businesses/{biz['business_id']}/inventory/upload",
        files={"file": ("bad.csv", io.BytesIO(b"price,stock\n10,5\n"), "text/csv")},
    )
    assert r.status_code == 400


def test_inventory_clear(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    client.post(f"/api/businesses/{bid}/inventory/upload",
               files={"file": ("v1.csv", io.BytesIO(b"name,price\nItem,10\n"), "text/csv")})
    r = client.delete(f"/api/businesses/{bid}/inventory")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    assert client.get(f"/api/businesses/{bid}/inventory").json() == []


def test_knowledge_mutations_touch_freshness(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    # force the stored timestamp artificially backward so we can detect a real update
    fake_db.businesses.docs[0]["knowledge_last_updated_at"] = "2020-01-01T00:00:00+00:00"

    client.post("/api/knowledge/manual", json={"business_id": bid, "title": "T", "text": "Some knowledge text."})
    after = fake_db.businesses.docs[0]["knowledge_last_updated_at"]
    assert after != "2020-01-01T00:00:00+00:00"
    assert after.startswith("20") and "T" in after  # looks like a fresh ISO timestamp


def test_businesses_needing_nudge(fake_db):
    import asyncio
    import freshness

    fake_db.businesses.docs.append({
        "business_id": "biz_stale", "email": "stale@example.com", "name": "Stale Biz",
        "knowledge_last_updated_at": "2020-01-01T00:00:00+00:00", "last_nudge_sent_at": None,
    })
    fake_db.businesses.docs.append({
        "business_id": "biz_fresh", "email": "fresh@example.com", "name": "Fresh Biz",
        "knowledge_last_updated_at": None, "created_at": "2020-01-01T00:00:00+00:00",
    })
    import datetime
    fake_db.businesses.docs[-1]["knowledge_last_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    freshness.db = fake_db
    result = asyncio.run(freshness.businesses_needing_nudge())
    ids = [b["business_id"] for b in result]
    assert "biz_stale" in ids
    assert "biz_fresh" not in ids
