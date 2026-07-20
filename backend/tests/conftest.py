"""Shared pytest fixtures.

Runs the real FastAPI app against an in-memory fake Mongo (tests/fakemongo.py)
instead of a live database, and mocks the Gemini calls in llm.py so tests never
need a real GEMINI_API_KEY or network access. This makes the suite fast, free,
and fully offline -- run with: pip install -r requirements-dev.txt && pytest
"""
import os
import sys
import types
import pytest

os.environ.setdefault("ENV", "development")
os.environ.setdefault("MONGO_URL", "mongodb://fake")
os.environ.setdefault("DB_NAME", "test_ai_employee")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fakemongo import FakeDB  # noqa: E402

_shared_fake_db = FakeDB()

# ---- stub motor so db.py imports cleanly without the real driver ----
motor_mod = types.ModuleType("motor")
motor_asyncio_mod = types.ModuleType("motor.motor_asyncio")


class _FakeMotorClient:
    def __init__(self, *a, **kw):
        pass

    def __getitem__(self, name):
        return _shared_fake_db

    def close(self):
        pass


motor_asyncio_mod.AsyncIOMotorClient = _FakeMotorClient
motor_mod.motor_asyncio = motor_asyncio_mod
sys.modules["motor"] = motor_mod
sys.modules["motor.motor_asyncio"] = motor_asyncio_mod


@pytest.fixture(autouse=True)
def reset_db():
    _shared_fake_db._collections.clear()
    yield _shared_fake_db


@pytest.fixture
def fake_db():
    return _shared_fake_db


@pytest.fixture
def mock_llm(monkeypatch):
    """Replaces real Gemini calls with deterministic canned responses."""
    import llm

    async def fake_rag_answer(business_name, business_context, history, question, **kw):
        return f"[MOCKED ANSWER for {business_name}] Regarding '{question}': see our info above."

    async def fake_owner_chat_reply(system, question):
        return "[MOCKED OWNER REPLY] Got it."

    async def fake_snapshot(business_name, category, combined_text):
        return "**What we found**\n- mocked snapshot"

    monkeypatch.setattr(llm, "rag_answer", fake_rag_answer)
    monkeypatch.setattr(llm, "owner_chat_reply", fake_owner_chat_reply)
    monkeypatch.setattr(llm, "generate_business_snapshot", fake_snapshot)
    # Also patch the references already imported into router modules
    import routers.chat as chat_router
    import routers.owner_chat as owner_chat_router
    import routers.businesses as businesses_router
    monkeypatch.setattr(chat_router, "rag_answer", fake_rag_answer)
    monkeypatch.setattr(owner_chat_router, "owner_chat_reply", fake_owner_chat_reply)
    monkeypatch.setattr(businesses_router, "generate_business_snapshot", fake_snapshot)


@pytest.fixture
def client(mock_llm):
    from fastapi.testclient import TestClient
    import server
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def signed_up_owner(client):
    """Creates a fresh owner account and returns (client-with-cookie, user_dict)."""
    r = client.post("/api/auth/signup", json={
        "email": "owner@example.com", "password": "supersecret1", "name": "Test Owner",
    })
    assert r.status_code == 200, r.text
    return client, r.json()
