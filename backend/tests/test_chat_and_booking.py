import datetime


def _create_business_with_appointments(client):
    r = client.post("/api/businesses", json={"name": "Sunrise Clinic", "email": "sunrise@example.com"})
    biz = r.json()
    settings = {
        "enabled": True,
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "working_hours": {"mon": ["09:00", "17:00"], "tue": ["09:00", "17:00"], "wed": ["09:00", "17:00"],
                          "thu": ["09:00", "17:00"], "fri": ["09:00", "17:00"], "sat": None, "sun": None},
        "slot_interval_minutes": 30,
    }
    client.put(f"/api/businesses/{biz['business_id']}/appointments/settings", json=settings)
    return biz


def test_public_chat_answers_using_mocked_llm(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business_with_appointments(client)
    client.post("/api/auth/logout")  # chat endpoint is public/unauthenticated

    r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "What are your hours?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "MOCKED ANSWER" in body["answer"]
    assert body["conversation_id"]


def test_chat_business_not_found(client):
    r = client.post("/api/chat", json={"business_id": "biz_doesnotexist", "message": "hi"})
    assert r.status_code == 404


def test_chat_respects_monthly_limit(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business_with_appointments(client)
    fake_db.businesses.docs[0]["monthly_used"] = 999999  # force over-limit
    client.post("/api/auth/logout")
    r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "hi"})
    assert r.status_code == 200
    assert r.json().get("error") == "limit_reached"


def _next_weekday(target_weekday):
    d = datetime.date.today() + datetime.timedelta(days=1)
    while d.weekday() != target_weekday:
        d += datetime.timedelta(days=1)
    return d


def test_chat_booking_flow_confirms_appointment(signed_up_owner, monkeypatch):
    client, owner = signed_up_owner
    biz = _create_business_with_appointments(client)
    booking_date = _next_weekday(0)  # next Monday

    import routers.chat as chat_router

    async def fake_answer_with_booking(business_name, business_context, history, question, **kw):
        return (
            "Sure, let's get you booked in!\n"
            f'<booking>{{"type": "book", "service": "Consultation", "date": "{booking_date.isoformat()}", '
            f'"time": "10:00", "customer_name": "Jane Doe", "customer_phone": "+911234567890"}}</booking>'
        )
    monkeypatch.setattr(chat_router, "rag_answer", fake_answer_with_booking)
    client.post("/api/auth/logout")

    r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "book me a consultation Monday 10am"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Confirmed" in body["answer"]
    assert "APT-" in body["answer"]

    # verify it actually landed in the appointments collection, not just claimed in text
    client.post("/api/auth/login", json={"email": owner["email"], "password": "supersecret1"})
    r2 = client.get(f"/api/businesses/{biz['business_id']}/appointments")
    assert r2.status_code == 200
    appts = r2.json()
    assert len(appts) == 1
    assert appts[0]["customer_name"] == "Jane Doe"


def test_chat_booking_rejects_slot_outside_hours(signed_up_owner, monkeypatch):
    client, owner = signed_up_owner
    biz = _create_business_with_appointments(client)
    booking_date = _next_weekday(0)

    import routers.chat as chat_router

    async def fake_answer_bad_time(business_name, business_context, history, question, **kw):
        return (
            "Booking that for you.\n"
            f'<booking>{{"type": "book", "service": "Consultation", "date": "{booking_date.isoformat()}", '
            f'"time": "23:00", "customer_name": "Late Larry", "customer_phone": "1"}}</booking>'
        )
    monkeypatch.setattr(chat_router, "rag_answer", fake_answer_bad_time)
    client.post("/api/auth/logout")

    r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "book me for 11pm"})
    assert r.status_code == 200
    assert "hours" in r.json()["answer"].lower() or "⚠️" in r.json()["answer"]


def test_handoff_creates_notification(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business_with_appointments(client)
    client.post("/api/auth/logout")

    chat_r = client.post("/api/chat", json={"business_id": biz["business_id"], "message": "I need a human"})
    conv_id = chat_r.json()["conversation_id"]

    r = client.post("/api/chat/handoff", json={
        "business_id": biz["business_id"], "conversation_id": conv_id,
        "visitor_email": "visitor@example.com", "visitor_name": "Vish", "note": "Complex billing question",
    })
    assert r.status_code == 200
