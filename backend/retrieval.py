"""Lightweight BM25-based retrieval for RAG.
Uses in-memory index per business_id, rebuilt from Mongo on demand and cached.
"""
import re
from typing import List, Tuple
from rank_bm25 import BM25Okapi
from db import db

_STOP = set("a an and or the of to in for on with is are was were be been being it its this that these those i you he she we they them our your as at by from if not but so do does did have has had will would can could should".split())

_cache: dict[str, dict] = {}  # business_id -> {"bm25":..., "docs":[chunk dicts], "version":int}


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


async def rebuild_index(business_id: str):
    docs = await db.knowledge_chunks.find({"business_id": business_id}, {"_id": 0}).to_list(5000)
    if not docs:
        _cache[business_id] = {"bm25": None, "docs": [], "version": 0}
        return
    corpus = [d.get("tokens") or tokenize(d["text"]) for d in docs]
    bm25 = BM25Okapi(corpus)
    _cache[business_id] = {"bm25": bm25, "docs": docs, "version": _cache.get(business_id, {}).get("version", 0) + 1}


async def search(business_id: str, query: str, k: int = 5) -> List[Tuple[dict, float]]:
    if business_id not in _cache:
        await rebuild_index(business_id)
    entry = _cache.get(business_id) or {}
    bm25 = entry.get("bm25")
    docs = entry.get("docs") or []
    if not bm25 or not docs:
        return []
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    scores = bm25.get_scores(q_tokens)
    # BM25 IDF collapses (goes negative) on tiny corpora. Use max(BM25_clipped, lex_overlap)
    # so retrieval always works — even with a single document.
    q_set = set(q_tokens)
    combined = []
    for s, d in zip(scores, docs):
        toks = d.get("tokens") or []
        tset = set(toks)
        overlap_ratio = len(q_set & tset) / max(len(q_set), 1)  # 0..1
        combined.append(max(float(s), 0.0) + overlap_ratio)
    ranked = sorted(zip(docs, combined), key=lambda x: x[1], reverse=True)
    top = [(d, float(s)) for d, s in ranked[:k] if s > 0]
    return top


def invalidate(business_id: str):
    _cache.pop(business_id, None)
