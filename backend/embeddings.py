"""Text embeddings via Gemini, for hybrid semantic + BM25 retrieval (see retrieval.py).

Deliberately isolated from llm.py's chat generation: embeddings use a different model and
a fire-and-forget failure mode. Every public function here swallows its own errors and
returns None (or a list of Nones) rather than raising -- an embedding outage should degrade
search quality (falls back to BM25), not take down the chat endpoint. This is what "hybrid
semantic search with BM25 fallback" means in practice, not just at index-build time.
"""
import logging
import math
from typing import List, Optional

from google import genai
from google.genai import types

import config

logger = logging.getLogger("roviq-ai.embeddings")

_client: Optional[genai.Client] = None

# RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY are Gemini's asymmetric embedding task types --
# using the right one for each side measurably improves retrieval quality over embedding
# both with a generic task type, since the model optimizes documents and queries differently.
TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


def _get_client() -> Optional[genai.Client]:
    global _client
    if _client is None and config.GEMINI_API_KEY:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


async def embed_texts(texts: List[str], task_type: str = TASK_DOCUMENT) -> List[Optional[List[float]]]:
    """Best-effort batch embedding. Returns one entry per input text, in order; any entry
    can be None (client not configured, API error, empty text) -- callers must handle a
    partially-None list, not just an all-or-nothing result."""
    if not texts:
        return []
    client = _get_client()
    if client is None:
        return [None] * len(texts)
    clean = [(t or "").strip()[:8000] for t in texts]  # Gemini embedding inputs have a token ceiling
    try:
        resp = await client.aio.models.embed_content(
            model=config.GEMINI_EMBEDDING_MODEL,
            contents=clean,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        out = [(e.values if e and e.values else None) for e in (resp.embeddings or [])]
        # Defensive: the API is expected to return one embedding per input in order, but if
        # it ever returns a short list, pad rather than let a zip() elsewhere silently drop items.
        while len(out) < len(clean):
            out.append(None)
        return out
    except Exception as e:
        logger.warning("Embedding call failed (%d texts, task=%s): %s", len(texts), task_type, e)
        return [None] * len(texts)


async def embed_one(text: str, task_type: str = TASK_QUERY) -> Optional[List[float]]:
    result = await embed_texts([text], task_type=task_type)
    return result[0] if result else None


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    # Gemini embeddings are near-unit-length already, but normalize explicitly rather than
    # assume it -- costs nothing and makes this correct regardless of model/version.
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
