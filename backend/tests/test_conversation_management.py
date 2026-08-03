def _create_business(client, **overrides):
    payload = {"name": "Conv Mgmt Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def _new_conversation(client, business_id, message="Do you have parking available?"):
    client.post("/api/auth/logout")
    r = client.post("/api/chat", json={"business_id": business_id, "message": message})
    return r.json()["conversation_id"]


def test_new_conversation_gets_auto_generated_title(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])

    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})
    r = client.get(f"/api/conversations/{conv_id}")
    assert r.status_code == 200
    conv = r.json()["conversation"]
    assert conv["title"] == "Mocked conversation title"
    assert conv["title_auto_generated"] is True
    assert conv["pinned"] is False
    assert conv["archived"] is False


def test_rename_conversation_marks_not_auto_generated(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    r = client.patch(f"/api/conversations/{conv_id}/title", json={"title": "Parking question"})
    assert r.status_code == 200

    conv = client.get(f"/api/conversations/{conv_id}").json()["conversation"]
    assert conv["title"] == "Parking question"
    assert conv["title_auto_generated"] is False


def test_pin_and_unpin_conversation(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    client.patch(f"/api/conversations/{conv_id}/pin", json={"pinned": True})
    conv = client.get(f"/api/conversations/{conv_id}").json()["conversation"]
    assert conv["pinned"] is True

    client.patch(f"/api/conversations/{conv_id}/pin", json={"pinned": False})
    conv = client.get(f"/api/conversations/{conv_id}").json()["conversation"]
    assert conv["pinned"] is False


def test_pinned_conversations_sort_first(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv1 = _new_conversation(client, biz["business_id"], "first question")
    conv2 = _new_conversation(client, biz["business_id"], "second question")
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    client.patch(f"/api/conversations/{conv1}/pin", json={"pinned": True})
    items = client.get(f"/api/conversations/business/{biz['business_id']}").json()
    assert items[0]["conversation_id"] == conv1  # pinned, even though it's the older conversation


def test_archive_hides_from_default_list(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    client.patch(f"/api/conversations/{conv_id}/archive", json={"archived": True})

    default_list = client.get(f"/api/conversations/business/{biz['business_id']}").json()
    assert conv_id not in [c["conversation_id"] for c in default_list]

    archived_list = client.get(f"/api/conversations/business/{biz['business_id']}", params={"archived": True}).json()
    assert conv_id in [c["conversation_id"] for c in archived_list]


def test_delete_conversation_removes_messages_too(signed_up_owner, fake_db):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    r = client.delete(f"/api/conversations/{conv_id}")
    assert r.status_code == 200
    assert not any(c["conversation_id"] == conv_id for c in fake_db.conversations.docs)
    assert not any(m["conversation_id"] == conv_id for m in fake_db.messages.docs)


def test_owner_cannot_manage_another_owners_conversation(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])

    client.post("/api/auth/signup", json={"email": "intruder@example.com", "password": "password123", "name": "Intruder"})
    r = client.patch(f"/api/conversations/{conv_id}/pin", json={"pinned": True})
    assert r.status_code == 404
    r2 = client.delete(f"/api/conversations/{conv_id}")
    assert r2.status_code == 404


def test_search_matches_message_text(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv1 = _new_conversation(client, biz["business_id"], "Do you have parking available?")
    conv2 = _new_conversation(client, biz["business_id"], "What time do you close on Sundays?")
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    results = client.get(f"/api/conversations/business/{biz['business_id']}", params={"search": "parking"}).json()
    ids = [c["conversation_id"] for c in results]
    assert conv1 in ids
    assert conv2 not in ids


def test_search_matches_renamed_title(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"], "totally unrelated text")
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})
    client.patch(f"/api/conversations/{conv_id}/title", json={"title": "Billing dispute"})

    results = client.get(f"/api/conversations/business/{biz['business_id']}", params={"search": "billing"}).json()
    assert conv_id in [c["conversation_id"] for c in results]


def test_export_json_contains_messages(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"])
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    r = client.get(f"/api/conversations/{conv_id}/export", params={"format": "json"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["conversation"]["conversation_id"] == conv_id
    assert len(body["messages"]) == 2  # customer message + AI reply


def test_export_txt_is_downloadable_transcript(signed_up_owner):
    client, owner = signed_up_owner
    biz = _create_business(client)
    conv_id = _new_conversation(client, biz["business_id"], "Do you have parking available?")
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})

    r = client.get(f"/api/conversations/{conv_id}/export", params={"format": "txt"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "attachment" in r.headers["content-disposition"]
    assert "Customer: Do you have parking available?" in r.text
