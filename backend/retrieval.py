"""Hybrid retrieval for RAG: semantic (Gemini embeddings) + BM25, with BM25 as the
automatic fallback whenever an embedding is missing (API outage, not yet backfilled, or
GEMINI_API_KEY unset). Also owns the single insertion point for knowledge_chunks
(index_chunks) and the tier classification (classify_tier) that context_builder.py uses
to enforce source-priority ordering.

In-memory BM25 index per business_id, rebuilt from Mongo on demand and cached -- unchanged
from before. Embeddings are stored per-chunk in Mongo (not re-embedded per search), so the
cost of hybrid search is one embedding call for the query, not the whole corpus.
"""
import re
from typing import List, Tuple, Optional
from rank_bm25 import BM25Okapi
from db import db
from embeddings import embed_texts, embed_one, cosine_similarity, TASK_DOCUMENT, TASK_QUERY

_STOP = set("a an and or the of to in for on with is are was were be been being it its this that these those i you he she we they them our your as at by from if not but so do does did have has had will would can could should".split())

_cache: dict = {}  # business_id -> {"bm25":..., "docs":[chunk dicts], "version":int}

# Small additive bonus applied after lexical/semantic scoring so a FAQ or uploaded document
# outranks an equally-relevant crawled page or generic note when their raw scores are close --
# this is what "source prioritization" means for the *retrieved* tiers (structured tiers like
# Quick Facts and business profile are handled separately in context_builder.py and are never
# subject to retrieval ranking at all -- they're always included in full).
TIER_BONUS = {"faq": 0.15, "document": 0.10, "crawl": 0.05, "inventory": 0.03, "manual": 0.0}


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def classify_tier(chunk: dict) -> str:
    """Maps a knowledge_chunks doc onto one of the retrieved-content tiers (faq, document,
    crawl, inventory, manual) from whatever it already has (source_type if set explicitly,
    otherwise inferred from the `source` field's existing conventions: "file:<id>" for
    uploads, an http(s) URL for crawled pages). Deliberately doesn't require a schema
    migration -- every existing chunk classifies correctly under the conventions already
    in use across knowledge.py/businesses.py/actions.py."""
    st = chunk.get("source_type")
    if st in ("faq", "inventory"):
        return st
    src = chunk.get("source") or ""
    if src.startswith("file:"):
        return "document"
    if src.startswith("http://") or src.startswith("https://"):
        return "crawl"
    return "manual"


async def index_chunks(docs: List[dict]) -> int:
    """The single insertion point for knowledge_chunks. Computes tokens (BM25) and best-
    effort embeddings (semantic) for every doc, inserts them, and invalidates the cache for
    every affected business. Every code path that creates chunks -- manual entries,
    uploads, crawls, inventory, and the owner-chat AI's add_knowledge/answer_unanswered
    actions -- goes through this instead of calling insert_many directly, so embedding
    coverage and cache invalidation aren't something each call site has to remember."""
    if not docs:
        return 0
    vectors = await embed_texts([d["text"] for d in docs], task_type=TASK_DOCUMENT)
    for d, vec in zip(docs, vectors):
        d["tokens"] = tokenize(d["text"])
        if vec is not None:
            d["embedding"] = vec
    await db.knowledge_chunks.insert_many(docs)
    for biz_id in {d["business_id"] for d in docs}:
        invalidate(biz_id)
    return len(docs)


async def rebuild_index(business_id: str):
    docs = await db.knowledge_chunks.find({"business_id": business_id}, {"_id": 0}).to_list(5000)
    if not docs:
        _cache[business_id] = {"bm25": None, "docs": [], "version": 0}
        return
    corpus = [d.get("tokens") or tokenize(d["text"]) for d in docs]
    bm25 = BM25Okapi(corpus)
    _cache[business_id] = {"bm25": bm25, "docs": docs, "version": _cache.get(business_id, {}).get("version", 0) + 1}


def _bm25_normalize(raw: float) -> float:
    """Squashes BM25's unbounded raw score into [0, 1) with a saturating curve, so it's
    comparable to (and combinable with) the semantic cosine-similarity score, which is
    already naturally 0..1. Without this, BM25's scale varies with corpus size and term
    rarity in a way that made the old "confidence" (compared against a fixed threshold)
    more of a coincidence than a real calibration."""
    return raw / (raw + 3.0) if raw > 0 else 0.0


async def hybrid_search(business_id: str, query: str, k: int = 6,
                        semantic_weight: float = 0.6) -> List[Tuple[dict, float]]:
    """Returns up to k (chunk, score) pairs, score in [0, 1], highest first. Blends
    normalized BM25 with semantic cosine similarity when both are available for a given
    chunk; falls back to BM25-only (lexical) when the query or a chunk has no embedding --
    e.g. GEMINI_API_KEY unset, an embedding call failed, or a chunk predates this feature
    and hasn't been backfilled yet. A small per-tier bonus (TIER_BONUS) nudges the ranking
    toward higher-priority sources (FAQ > document > crawl > inventory > generic note) when
    scores are otherwise close."""
    if business_id not in _cache:
        await rebuild_index(business_id)
    entry = _cache.get(business_id) or {}
    docs = entry.get("docs") or []
    if not docs:
        return []
    bm25 = entry.get("bm25")
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    q_set = set(q_tokens)
    bm25_scores = bm25.get_scores(q_tokens) if bm25 else [0.0] * len(docs)
    q_vec: Optional[List[float]] = await embed_one(query, task_type=TASK_QUERY)

    scored = []
    for doc, raw_bm25 in zip(docs, bm25_scores):
        toks = set(doc.get("tokens") or [])
        overlap = len(q_set & toks) / max(len(q_set), 1)
        # BM25's IDF collapses (goes negative) on tiny corpora -- keep the lexical-overlap
        # floor so retrieval still works with only a handful of documents indexed.
        lexical = max(_bm25_normalize(float(raw_bm25)), overlap * 0.5)

        chunk_vec = doc.get("embedding")
        if q_vec is not None and chunk_vec:
            semantic = cosine_similarity(q_vec, chunk_vec)
            base = semantic_weight * semantic + (1 - semantic_weight) * lexical
        else:
            base = lexical  # BM25 fallback: no query embedding, or this chunk predates embeddings

        tier = classify_tier(doc)
        scored.append((doc, min(base + TIER_BONUS.get(tier, 0.0), 1.0)))

    ranked = sorted(scored, key=lambda x: x[1], reverse=True)
    return [(d, s) for d, s in ranked[:k] if s > 0.05]


async def search(business_id: str, query: str, k: int = 5) -> List[Tuple[dict, float]]:
    """Backward-compatible alias -- prefer hybrid_search directly in new code."""
    return await hybrid_search(business_id, query, k=k)


async def backfill_embeddings(business_id: str, batch_size: int = 50) -> int:
    """One-time (or periodic, via the weekly scheduler) pass that embeds any chunk created
    before this feature existed, or where a previous embedding call failed. Safe to call
    repeatedly -- only touches chunks missing `embedding`."""
    missing = await db.knowledge_chunks.find(
        {"business_id": business_id, "embedding": {"$exists": False}}, {"_id": 0, "id": 1, "text": 1},
    ).to_list(batch_size)
    if not missing:
        return 0
    vectors = await embed_texts([d["text"] for d in missing], task_type=TASK_DOCUMENT)
    updated = 0
    for d, vec in zip(missing, vectors):
        if vec is not None:
            await db.knowledge_chunks.update_one({"id": d["id"]}, {"$set": {"embedding": vec}})
            updated += 1
    if updated:
        invalidate(business_id)
    return updated


def invalidate(business_id: str):
    _cache.pop(business_id, None)
