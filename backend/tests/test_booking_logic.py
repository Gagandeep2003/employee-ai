import datetime
import pytest
import booking


BIZ_ID = "biz_slot_test"


@pytest.fixture(autouse=True)
def seed(fake_db):
    fake_db.businesses.docs.append({
        "business_id": BIZ_ID,
        "appointment_settings": {
            "enabled": True,
            "services": [{"name": "Consultation", "duration_minutes": 30}],
            "working_hours": {
                "mon": ["09:00", "12:00"], "tue": ["09:00", "12:00"], "wed": ["09:00", "12:00"],
                "thu": ["09:00", "12:00"], "fri": ["09:00", "12:00"], "sat": None, "sun": None,
            },
            "slot_interval_minutes": 30,
        },
    })


def _next_weekday(target_weekday, min_days_out=1):
    d = datetime.date.today() + datetime.timedelta(days=min_days_out)
    while d.weekday() != target_weekday:
        d += datetime.timedelta(days=1)
    return d


@pytest.mark.asyncio
async def test_slots_generated_within_hours():
    d = _next_weekday(0)  # Monday
    res = await booking.get_open_slots(BIZ_ID, "Consultation", d.isoformat())
    assert res["ok"]
    assert res["slots"] == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]


@pytest.mark.asyncio
async def test_closed_day_returns_no_slots():
    d = _next_weekday(5)  # Saturday
    res = await booking.get_open_slots(BIZ_ID, "Consultation", d.isoformat())
    assert res["ok"]
    assert res["slots"] == []


@pytest.mark.asyncio
async def test_book_then_slot_disappears():
    d = _next_weekday(0)
    r = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "09:00", "Test Customer", customer_phone="1")
    assert r["ok"], r
    slots = await booking.get_open_slots(BIZ_ID, "Consultation", d.isoformat())
    assert "09:00" not in slots["slots"]
    assert "09:30" in slots["slots"]


@pytest.mark.asyncio
async def test_double_booking_rejected():
    d = _next_weekday(1)
    r1 = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "10:00", "A", customer_phone="1")
    assert r1["ok"], r1
    r2 = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "10:00", "B", customer_phone="2")
    assert not r2["ok"]
    assert "taken" in r2["error"]


@pytest.mark.asyncio
async def test_outside_hours_rejected():
    d = _next_weekday(2)
    r = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "13:00", "A", customer_phone="1")
    assert not r["ok"]
    assert "hours" in r["error"]


@pytest.mark.asyncio
async def test_unknown_service_rejected():
    d = _next_weekday(3)
    r = await booking.book(BIZ_ID, "Massage", d.isoformat(), "10:00", "A", customer_phone="1")
    assert not r["ok"]
    assert "Unknown service" in r["error"]


@pytest.mark.asyncio
async def test_missing_contact_rejected():
    d = _next_weekday(4)
    r = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "10:00", "A")
    assert not r["ok"]
    assert "phone or email" in r["error"]


@pytest.mark.asyncio
async def test_cancel_and_rebook():
    d = _next_weekday(0, min_days_out=8)
    r1 = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "10:00", "A", customer_phone="1")
    ref = r1["reference"]
    c = await booking.cancel(BIZ_ID, ref)
    assert c["ok"]
    r2 = await booking.book(BIZ_ID, "Consultation", d.isoformat(), "10:00", "B", customer_phone="2")
    assert r2["ok"], r2


def test_parse_booking_tag():
    text = ('Sure, checking! <booking>{"type": "check_availability", '
            '"service": "Consultation", "date": "2026-08-01"}</booking>')
    clean, action = booking.parse_booking(text)
    assert clean == "Sure, checking!"
    assert action["type"] == "check_availability"


def test_parse_booking_no_tag_returns_none():
    clean, action = booking.parse_booking("Just a normal reply, no booking here.")
    assert action is None
    assert clean == "Just a normal reply, no booking here."
