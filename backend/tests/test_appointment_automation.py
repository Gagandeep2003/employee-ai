import datetime as dt


def _create_business(client, **overrides):
    payload = {"name": "Appt Automation Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


def _next_monday(days_ahead=1):
    d = dt.date.today() + dt.timedelta(days=days_ahead)
    while d.weekday() != 0:
        d += dt.timedelta(days=1)
    return d


def _enable_booking(client, bid, working_hours=None, holidays=None):
    r = client.put(f"/api/businesses/{bid}/appointments/settings", json={
        "enabled": True,
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "working_hours": working_hours or {"mon": ["09:00", "17:00"], "tue": ["09:00", "17:00"],
                                           "wed": None, "thu": None, "fri": None, "sat": None, "sun": None},
        "slot_interval_minutes": 30,
        "holidays": holidays or [],
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Timezone-aware booking
# ---------------------------------------------------------------------------
def test_invalid_timezone_rejected(signed_up_owner):
    client, _ = signed_up_owner
    r = client.post("/api/businesses", json={"name": "Bad TZ Biz", "timezone": "Mars/Colony_One"})
    assert r.status_code == 422


def test_booking_stores_utc_from_business_local_time(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client, timezone="Asia/Kolkata")
    bid = biz["business_id"]
    _enable_booking(client, bid)

    monday = _next_monday()
    client.post("/api/auth/logout")
    r = client.post("/api/v1/appointments", headers={"X-Api-Key": "irrelevant"},
                    json={"service": "Consultation", "date": monday.isoformat(), "time": "09:00",
                          "customer_name": "Test", "customer_phone": "555"})
    # no valid API key -- expected 401, this just confirms the route exists; real booking test below
    assert r.status_code == 401


def test_booking_at_9am_local_ist_stores_as_330am_utc(signed_up_owner, fake_db):
    import booking
    client, _ = signed_up_owner
    biz = _create_business(client, timezone="Asia/Kolkata")
    bid = biz["business_id"]
    _enable_booking(client, bid)
    monday = _next_monday()

    import asyncio
    result = asyncio.run(booking.book(bid, "Consultation", monday.isoformat(), "09:00", "Jordan", "555-0100"))
    assert result["ok"], result

    stored = next(a for a in fake_db.appointments.docs if a["business_id"] == bid)
    start_utc = dt.datetime.fromisoformat(stored["start_time"])
    assert start_utc.tzinfo is not None
    assert start_utc.hour == 3 and start_utc.minute == 30  # 09:00 IST == 03:30 UTC (UTC+5:30)

    # the response's start_time is shown back in the business's own local time
    assert "09:00" in result["start_time"] or result["start_time"].endswith("+05:30")


def test_slots_returned_in_business_local_time(signed_up_owner):
    import booking
    import asyncio
    client, _ = signed_up_owner
    biz = _create_business(client, timezone="Asia/Kolkata")
    bid = biz["business_id"]
    _enable_booking(client, bid)
    monday = _next_monday()

    result = asyncio.run(booking.get_open_slots(bid, "Consultation", monday.isoformat()))
    assert result["ok"]
    assert "09:00" in result["slots"]  # not 03:30 (the UTC equivalent) -- shown in local time
    assert "17:00" not in result["slots"]  # closes at 17:00, last 30-min slot starts 16:30
    assert "16:30" in result["slots"]


def test_different_timezones_dont_collide_on_same_utc_moment(signed_up_owner):
    """A UTC-only implementation would treat '09:00' the same regardless of business --
    this confirms two businesses in different timezones get genuinely different UTC
    instants for the 'same' local booking time."""
    import booking
    import asyncio
    client, _ = signed_up_owner
    biz_ist = _create_business(client, name="IST Biz", timezone="Asia/Kolkata")
    biz_utc = _create_business(client, name="UTC Biz", timezone="UTC")
    _enable_booking(client, biz_ist["business_id"])
    _enable_booking(client, biz_utc["business_id"])
    monday = _next_monday()

    r1 = asyncio.run(booking.book(biz_ist["business_id"], "Consultation", monday.isoformat(), "09:00", "A", "111"))
    r2 = asyncio.run(booking.book(biz_utc["business_id"], "Consultation", monday.isoformat(), "09:00", "B", "222"))
    assert r1["ok"] and r2["ok"]
    t1 = dt.datetime.fromisoformat(r1["start_time"])
    t2 = dt.datetime.fromisoformat(r2["start_time"])
    # same wall-clock "09:00" in each business's own timezone, but genuinely different UTC instants
    assert t1.astimezone(dt.timezone.utc) != t2.astimezone(dt.timezone.utc)


# ---------------------------------------------------------------------------
# Holidays
# ---------------------------------------------------------------------------
def test_holiday_blocks_availability_and_booking(signed_up_owner):
    import booking
    import asyncio
    client, _ = signed_up_owner
    biz = _create_business(client, timezone="UTC")
    bid = biz["business_id"]
    monday = _next_monday()
    _enable_booking(client, bid, holidays=[monday.isoformat()])

    avail = asyncio.run(booking.get_open_slots(bid, "Consultation", monday.isoformat()))
    assert avail["ok"] and avail["slots"] == []
    assert "holiday" in avail.get("note", "").lower()

    result = asyncio.run(booking.book(bid, "Consultation", monday.isoformat(), "09:00", "Test", "555"))
    assert result["ok"] is False
    assert "holiday" in result["error"].lower()


def test_invalid_holiday_date_rejected(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    r = client.put(f"/api/businesses/{biz['business_id']}/appointments/settings", json={
        "enabled": True, "services": [], "working_hours": {}, "holidays": ["not-a-date"],
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Crawler-driven extraction + owner review
# ---------------------------------------------------------------------------
def _mock_crawl(monkeypatch, text: str):
    async def fake_crawl_site(website, max_pages=15):
        return [(website, "Home", text)]
    import routers.businesses as businesses_router
    monkeypatch.setattr(businesses_router, "crawl_site", fake_crawl_site)


def test_crawl_produces_appointment_draft_for_review(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _mock_crawl(monkeypatch, "We are open MONDAY 9AM TO 5PM for consultations. " * 5)

    r = client.post("/api/businesses", json={"name": "Crawled Biz", "website": "https://example.com"})
    bid = r.json()["business_id"]

    draft = client.get(f"/api/businesses/{bid}/appointments/settings/draft").json()
    assert draft is not None
    assert draft["working_hours"]["mon"] == ["09:00", "17:00"]
    assert draft["confidence"] == "high"

    # not applied automatically -- live settings are untouched
    live = client.get(f"/api/businesses/{bid}/appointments/settings").json()
    assert live["enabled"] is False


def test_no_draft_when_nothing_extractable(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    _mock_crawl(monkeypatch, "Welcome to our lovely shop, we sell wonderful things.")

    r = client.post("/api/businesses", json={"name": "Vague Biz", "website": "https://example.com"})
    bid = r.json()["business_id"]

    draft = client.get(f"/api/businesses/{bid}/appointments/settings/draft").json()
    assert draft is None


def test_no_draft_extraction_when_already_configured(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    _enable_booking(client, bid)  # owner already configured booking by hand

    _mock_crawl(monkeypatch, "We are open MONDAY 9AM TO 5PM for consultations. " * 5)
    client.post(f"/api/businesses/{bid}/recrawl")

    draft = client.get(f"/api/businesses/{bid}/appointments/settings/draft").json()
    assert draft is None  # not silently second-guessed


def test_publish_draft_applies_settings_and_clears_draft(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    # seed the draft directly (equivalent to what the crawl would have stored)
    from db import db
    import asyncio
    asyncio.run(db.businesses.update_one({"business_id": bid}, {"$set": {"appointment_settings_draft": {
        "working_hours": {"mon": ["09:00", "17:00"], "tue": None, "wed": None, "thu": None, "fri": None, "sat": None, "sun": None},
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "holidays": ["2026-12-25"], "timezone_guess": "Asia/Kolkata", "confidence": "high",
    }}}))

    r = client.post(f"/api/businesses/{bid}/appointments/settings/publish-draft")
    assert r.status_code == 200
    published = r.json()
    assert published["enabled"] is True
    assert published["working_hours"]["mon"] == ["09:00", "17:00"]
    assert published["holidays"] == ["2026-12-25"]

    biz_after = client.get(f"/api/businesses/{bid}").json()
    assert biz_after["timezone"] == "Asia/Kolkata"  # timezone guess applied too

    draft_after = client.get(f"/api/businesses/{bid}/appointments/settings/draft").json()
    assert draft_after is None


def test_dismiss_draft_leaves_settings_untouched(signed_up_owner):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    from db import db
    import asyncio
    asyncio.run(db.businesses.update_one({"business_id": bid}, {"$set": {"appointment_settings_draft": {
        "working_hours": {"mon": ["09:00", "17:00"]}, "services": [], "holidays": [], "confidence": "low",
    }}}))

    r = client.delete(f"/api/businesses/{bid}/appointments/settings/draft")
    assert r.status_code == 200
    assert client.get(f"/api/businesses/{bid}/appointments/settings/draft").json() is None
    assert client.get(f"/api/businesses/{bid}/appointments/settings").json()["enabled"] is False
