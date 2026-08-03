import pytest

import retrieval
import context_builder
import embeddings


def _create_business(client, **overrides):
    payload = {"name": "Retrieval Test Biz"}
    payload.update(overrides)
    r = client.post("/api/businesses", json=payload)
    return r.json()


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------
def test_classify_tier_faq():
    assert retrieval.classify_tier({"source_type": "faq"}) == "faq"


def test_classify_tier_inventory():
    assert retrieval.classify_tier({"source_type": "inventory"}) == "inventory"


def test_classify_tier_document():
    assert retrieval.classify_tier({"source": "file:abc123"}) == "document"


def test_classify_tier_crawl():
    assert retrieval.classify_tier({"source": "https://example.com/about"}) == "crawl"


def test_classify_tier_manual_default():
    assert retrieval.classify_tier({"source": "manual"}) == "manual"


# ---------------------------------------------------------------------------
# embeddings.py -- graceful degradation (no GEMINI_API_KEY in the test env,
# same as it would be for any deployment that hasn't set one)
# ---------------------------------------------------------------------------
async def test_embed_texts_returns_none_list_without_api_key():
    result = await embeddings.embed_texts(["hello", "world"])
    assert result == [None, None]


async def test_embed_one_returns_none_without_api_key():
    assert await embeddings.embed_one("hello") is None


def test_cosine_similarity_handles_missing_vectors():
    assert embeddings.cosine_similarity(None, [1, 2, 3]) == 0.0
    assert embeddings.cosine_similarity([1, 2, 3], []) == 0.0


def test_cosine_similarity_correct_for_known_vectors():
    assert embeddings.cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# index_chunks -- the single centralized insertion point
# ---------------------------------------------------------------------------
async def test_index_chunks_sets_tokens_and_skips_embedding_gracefully(fake_db):
    from datetime import datetime, timezone
    docs = [{"id": "chunk_idx_1", "business_id": "biz_idx_test", "text": "We open at nine and close at five",
             "source": "manual", "source_title": "Hours", "created_at": datetime.now(timezone.utc).isoformat()}]
    added = await retrieval.index_chunks(docs)
    assert added == 1
    stored = next(d for d in fake_db.knowledge_chunks.docs if d["id"] == "chunk_idx_1")
    assert stored["tokens"]
    assert "embedding" not in stored  # no GEMINI_API_KEY in the test env -- real fallback, not a fake vector


async def test_index_chunks_noop_on_empty_list():
    assert await retrieval.index_chunks([]) == 0


# ---------------------------------------------------------------------------
# context_builder -- structured tiers always present regardless of relevance
# ---------------------------------------------------------------------------
async def test_business_profile_tier_always_present(fake_db):
    biz = {"business_id": "biz_ctx_profile", "name": "Ctx Test Biz", "category": "Retail",
           "quick_facts": {}, "appointment_settings": {"enabled": False}}
    result = await context_builder.build_context(biz, "hello there")
    assert "TIER 3: BUSINESS PROFILE" in result["prompt_context"]
    assert "Ctx Test Biz" in result["prompt_context"]
    assert result["confidence"] == 0.0  # nothing relevant retrieved, no structured hit


async def test_appointment_tier_present_only_when_enabled(fake_db):
    biz_off = {"business_id": "biz_ctx_appt_off", "name": "No Booking Biz", "quick_facts": {},
              "appointment_settings": {"enabled": False}}
    result_off = await context_builder.build_context(biz_off, "do you take appointments")
    assert "TIER 2: APPOINTMENT SETTINGS" not in result_off["prompt_context"]

    biz_on = {"business_id": "biz_ctx_appt_on", "name": "Booking Biz", "quick_facts": {},
             "appointment_settings": {"enabled": True, "services": [{"name": "Haircut", "duration_minutes": 30}],
                                      "working_hours": {"mon": ["09:00", "17:00"]}}}
    result_on = await context_builder.build_context(biz_on, "do you take appointments")
    assert "TIER 2: APPOINTMENT SETTINGS" in result_on["prompt_context"]
    assert "Haircut" in result_on["prompt_context"]


# ---------------------------------------------------------------------------
# End-to-end via the real chat endpoint (mocked LLM captures what it was given)
# ---------------------------------------------------------------------------
def test_quick_facts_answer_even_with_zero_knowledge_chunks(signed_up_owner):
    """Regression test for a real bug caught during this pass: `unanswered` used to stay
    True whenever there were zero *retrieved* chunks, even if a structured tier (Quick
    Facts) fully answered the question -- e.g. a brand-new business with Quick Facts set
    but nothing crawled/uploaded yet."""
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    client.put(f"/api/businesses/{bid}/quick-facts", json={
        "hours_note": "We are open every day including all holidays", "special_or_promo": "", "announcement": "",
    })
    r = client.post("/api/chat", json={"business_id": bid, "message": "are you open on holidays"})
    body = r.json()
    assert body["unanswered"] is False
    assert body["confidence"] >= 0.8


def test_faq_tier_ranks_above_generic_note(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    client.post("/api/knowledge/manual", json={
        "business_id": bid, "title": "Return policy note", "kind": "note",
        "text": "Our return policy allows returns within thirty days of purchase for a full refund.",
    })
    client.post("/api/knowledge/manual", json={
        "business_id": bid, "title": "Return policy FAQ", "kind": "faq",
        "text": "Q: What is your return policy?\nA: Returns within thirty days of purchase for a full refund.",
    })

    import routers.chat as chat_router
    captured = {}

    async def fake_rag_answer(business_name, business_context, history, question, **kw):
        captured["business_context"] = business_context
        return "ok"
    monkeypatch.setattr(chat_router, "rag_answer", fake_rag_answer)

    client.post("/api/chat", json={"business_id": bid, "message": "what is your return policy"})
    ctx = captured["business_context"]
    faq_pos = ctx.find("[FAQ: Return policy FAQ")
    note_pos = ctx.find("[Note: Return policy note")
    assert faq_pos != -1 and note_pos != -1
    assert faq_pos < note_pos  # the FAQ tier bonus outranks an equally-relevant generic note


def test_tier_headers_appear_in_priority_order(signed_up_owner, monkeypatch):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]
    client.put(f"/api/businesses/{bid}/quick-facts", json={
        "hours_note": "Closing early today at 3pm", "special_or_promo": "", "announcement": "",
    })

    import routers.chat as chat_router
    captured = {}

    async def fake_rag_answer(business_name, business_context, history, question, **kw):
        captured["business_context"] = business_context
        return "ok"
    monkeypatch.setattr(chat_router, "rag_answer", fake_rag_answer)

    client.post("/api/chat", json={"business_id": bid, "message": "what time do you close"})
    ctx = captured["business_context"]
    t1, t3 = ctx.find("TIER 1"), ctx.find("TIER 3")
    assert t1 != -1 and t3 != -1 and t1 < t3


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------
def test_conversation_summary_generated_after_threshold(signed_up_owner, fake_db):
    client, _ = signed_up_owner
    biz = _create_business(client)
    bid = biz["business_id"]

    conv_id = None
    for i in range(7):  # 7 turns = 14 messages, crossing the 12-message summarization threshold
        r = client.post("/api/chat", json={"business_id": bid, "conversation_id": conv_id, "message": f"question {i}"})
        conv_id = r.json()["conversation_id"]

    conv = next(c for c in fake_db.conversations.docs if c["conversation_id"] == conv_id)
    assert conv.get("summary")
    assert "MOCKED SUMMARY" in conv["summary"]
