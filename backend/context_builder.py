"""Assembles the priority-ordered context for the customer-facing chat.

Priority order (highest first): Quick Facts (owner-set, always-current) -> appointment
settings -> business profile -> retrieved knowledge (FAQ > uploaded documents > website
crawl > inventory/generic notes) -> the model's own general knowledge, last resort only.

The first three tiers are structured data pulled straight from the business document --
small and bounded, so they're always included in full regardless of query relevance, and
are explicitly labeled in the prompt as authoritative and non-negotiable. This is the
mechanism (combined with the instruction text in llm.rag_answer) behind "structured
business data can never be overridden by the model": it's always in context, always
labeled highest-priority, and the retrieved tiers below it are explicitly told they lose
any conflict. This is a strong prompting guarantee, not a hard code-level one -- an LLM can
in principle still deviate -- but it's the correct, standard mitigation short of that.
"""
import re
from typing import Any, Dict, List, Tuple

from retrieval import hybrid_search, classify_tier
from freshness import days_since

TIER_LABELS = {"faq": "FAQ", "document": "Uploaded document", "crawl": "Website", "inventory": "Inventory", "manual": "Note"}
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _age_note(iso: str) -> str:
    age = days_since(iso)
    if age == 0:
        return "today"
    if age < 9999:
        return f"{age}d ago"
    return "unknown age"


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _quick_facts_block(biz: dict) -> Tuple[str, bool]:
    qf = biz.get("quick_facts") or {}
    lines = [v for v in (qf.get("hours_note"), qf.get("special_or_promo"), qf.get("announcement")) if v]
    if not lines:
        return "", False
    age = _age_note(qf.get("updated_at"))
    body = "\n".join(f"- {l}" for l in lines)
    block = (
        f"=== TIER 1: OWNER-CONFIRMED FACTS (set directly by the business owner, updated {age}) ===\n"
        f"These are ALWAYS TRUE and take priority over everything else in this prompt, including "
        f"anything below that seems to say otherwise.\n{body}"
    )
    return block, True


def _appointment_block(settings: dict) -> str:
    if not settings or not settings.get("enabled"):
        return ""
    services = settings.get("services") or []
    svc_line = ", ".join(f"{s['name']} ({s.get('duration_minutes', 30)}min)" for s in services) or "(none configured)"
    hours = settings.get("working_hours") or {}
    hour_line = "; ".join(
        f"{d} {h[0]}-{h[1]}" if (h := hours.get(d)) else f"{d} closed" for d in DAY_KEYS
    )
    return (
        "=== TIER 2: APPOINTMENT SETTINGS (owner-configured, authoritative) ===\n"
        f"Services: {svc_line}\nHours: {hour_line}"
    )


def _business_profile_block(biz: dict) -> str:
    lines = [f"Name: {biz['name']}"]
    for label, key in [("Category", "category"), ("Website", "website"), ("Phone", "phone"),
                       ("Contact email", "email"), ("Country", "country")]:
        if biz.get(key):
            lines.append(f"{label}: {biz[key]}")
    return "=== TIER 3: BUSINESS PROFILE (authoritative) ===\n" + "\n".join(lines)


async def build_context(biz: dict, query: str, k: int = 6) -> Dict[str, Any]:
    """Returns {prompt_context, confidence, sources, structured_hit}. `prompt_context` is
    the full tiered block ready to hand straight to llm.rag_answer as `business_context`.
    `confidence` is 0..1 -- see hybrid_search for how the retrieved-tier component is
    computed; a direct hit on Tier 1/2/3 (structured, owner-confirmed data) floors it at
    0.8 regardless of retrieval score, since that's ground truth by definition."""
    sections: List[str] = []
    q_tokens = _tokens(query)
    structured_hit = False

    qf_block, qf_present = _quick_facts_block(biz)
    if qf_block:
        sections.append(qf_block)
        if qf_present and q_tokens & _tokens(qf_block):
            structured_hit = True

    appt_block = _appointment_block(biz.get("appointment_settings") or {})
    if appt_block:
        sections.append(appt_block)
        if q_tokens & _tokens(appt_block):
            structured_hit = True

    sections.append(_business_profile_block(biz))

    hits = await hybrid_search(biz["business_id"], query, k=k)
    top_score = hits[0][1] if hits else 0.0
    if hits:
        retrieved_lines = []
        for chunk, _score in hits:
            tier = classify_tier(chunk)
            label = TIER_LABELS.get(tier, "Note")
            title = chunk.get("source_title") or chunk.get("source") or "Untitled"
            retrieved_lines.append(f"[{label}: {title}, updated {_age_note(chunk.get('created_at'))}]\n{chunk['text']}")
        sections.append(
            "=== RETRIEVED KNOWLEDGE (ranked by relevance to the question; if two sources "
            "disagree, trust the one listed first, and TIERS 1-3 above always win over any "
            "of these) ===\n\n" + "\n\n".join(retrieved_lines)
        )

    confidence = max(top_score, 0.8) if structured_hit else top_score

    return {
        "prompt_context": "\n\n".join(sections),
        "confidence": round(min(confidence, 1.0), 3),
        "sources": [
            {"title": h[0].get("source_title") or h[0].get("source"), "source": h[0].get("source"),
             "tier": classify_tier(h[0])}
            for h in hits[:3]
        ],
        "structured_hit": structured_hit,
    }
