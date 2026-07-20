"""Owner-side action registry — the AI Employee can perform these on behalf of the owner.
The LLM emits a JSON action block; this module validates and executes it against MongoDB.

Design: the AI returns text like:
  "Sure, updating your hours now.
   <action>{"type":"update_business","fields":{"phone":"..."}}</action>"

Backend extracts the JSON, runs the corresponding handler, returns a confirmation.
"""
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import db
from retrieval import invalidate, tokenize

# Regex to pull the JSON block out of the LLM's reply
ACTION_RE = re.compile(r"<action>\s*(\{.*?\})\s*</action>", re.DOTALL)

ALLOWED_BUSINESS_FIELDS = {"name", "website", "email", "phone", "category", "country", "language", "timezone"}
ALLOWED_WIDGET_FIELDS = {"primary_color", "accent_color", "welcome_message", "position", "logo_url", "show_branding"}

ACTION_SCHEMAS = """You can OPTIONALLY perform one action per reply. Emit at the very end of your message a single line:
<action>{"type": "<one_of>", ...}</action>

Available actions:

1) update_business — change business profile fields
   { "type": "update_business", "fields": { "phone": "…", "email": "…", "name": "…", "category": "…", "country": "…", "language": "…", "timezone": "…", "website": "…" } }

2) update_widget — change chat widget appearance
   { "type": "update_widget", "fields": { "primary_color": "#1E3F33", "accent_color": "#C4A47C", "welcome_message": "…", "position": "bottom-right", "show_branding": true } }

3) add_knowledge — add a Q&A / info entry to the AI's knowledge base
   { "type": "add_knowledge", "title": "…", "text": "…" }

4) answer_unanswered — teach a specific answer for a previously unanswered question
   { "type": "answer_unanswered", "question": "…", "answer": "…" }

5) delete_knowledge — remove knowledge chunks matching a title/keyword (destructive; only when the owner clearly asks)
   { "type": "delete_knowledge", "match": "keyword or exact title" }

6) list_knowledge — list current knowledge entries (returns titles); use before deleting
   { "type": "list_knowledge" }

7) update_appointment_settings — turn on/configure appointment booking for the customer-facing AI
   { "type": "update_appointment_settings", "fields": { "enabled": true,
       "services": [{"name": "Consultation", "duration_minutes": 30}],
       "working_hours": {"mon": ["09:00","17:00"], "tue": ["09:00","17:00"], "wed": ["09:00","17:00"], "thu": ["09:00","17:00"], "fri": ["09:00","17:00"], "sat": null, "sun": null},
       "slot_interval_minutes": 30 } }
   Only include days that are open; omit or set null for closed days. Always include the FULL service list and FULL week (all 7 days) since this replaces the previous settings entirely.

8) list_appointments — list upcoming confirmed appointments
   { "type": "list_appointments" }

9) update_quick_facts — set short, fast-changing facts (today's hours, a promo, a temporary
   closure/announcement). This is the fastest way for an owner to keep the AI current without
   re-crawling or editing knowledge chunks -- always trusted over older crawled content.
   { "type": "update_quick_facts", "fields": { "hours_note": "Open till 9pm today", "special_or_promo": "20% off all shirts this weekend", "announcement": "" } }
   Only include the fields the owner actually mentioned; leave others out of "fields" to keep them unchanged.

RULES:
- Emit an action ONLY when the owner clearly requests a change/write. For read questions, answer in plain text without an action.
- For destructive actions (delete_knowledge), first do list_knowledge if the owner is vague, otherwise use the exact match string they provided.
- For update_appointment_settings, if the owner hasn't told you their services/hours yet, ask for them in plain text first (no action) rather than guessing.
- Never invent data. If the owner asks for a change that requires info you don't have, ask them for it (plain text, no action).
- ALWAYS include a friendly one-line confirmation BEFORE the <action> tag so the owner knows what will happen.
"""


def parse_action(text: str) -> tuple[str, Optional[dict]]:
    """Extract action JSON from LLM reply. Returns (clean_text, action_dict)."""
    m = ACTION_RE.search(text)
    if not m:
        return text.strip(), None
    try:
        action = json.loads(m.group(1))
    except Exception:
        return text.strip(), None
    clean = ACTION_RE.sub("", text).strip()
    return clean, action


async def execute_action(business_id: str, action: dict) -> dict:
    """Run one action. Returns {'ok': bool, 'result': ..., 'error': ..., 'action': ...}."""
    try:
        atype = action.get("type")
        if atype == "update_business":
            fields = {k: v for k, v in (action.get("fields") or {}).items() if k in ALLOWED_BUSINESS_FIELDS and v is not None}
            if not fields:
                return {"ok": False, "error": "No valid fields to update", "action": atype}
            await db.businesses.update_one({"business_id": business_id}, {"$set": fields})
            return {"ok": True, "result": {"updated_fields": list(fields.keys())}, "action": atype}

        if atype == "update_widget":
            fields = {k: v for k, v in (action.get("fields") or {}).items() if k in ALLOWED_WIDGET_FIELDS and v is not None}
            if not fields:
                return {"ok": False, "error": "No valid widget fields", "action": atype}
            update = {f"widget.{k}": v for k, v in fields.items()}
            await db.businesses.update_one({"business_id": business_id}, {"$set": update})
            return {"ok": True, "result": {"widget_updated": list(fields.keys())}, "action": atype}

        if atype == "add_knowledge":
            title = (action.get("title") or "").strip() or "Note"
            text = (action.get("text") or "").strip()
            if len(text) < 5:
                return {"ok": False, "error": "Text too short", "action": atype}
            await db.knowledge_chunks.insert_one({
                "id": str(uuid.uuid4()), "business_id": business_id,
                "text": text, "source": "manual", "source_title": title,
                "tokens": tokenize(text),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            invalidate(business_id)
            return {"ok": True, "result": {"title": title}, "action": atype}

        if atype == "answer_unanswered":
            q = (action.get("question") or "").strip()
            a = (action.get("answer") or "").strip()
            if not q or not a:
                return {"ok": False, "error": "question and answer required", "action": atype}
            combined = f"Q: {q}\nA: {a}"
            await db.knowledge_chunks.insert_one({
                "id": str(uuid.uuid4()), "business_id": business_id,
                "text": combined, "source": "manual", "source_title": q[:80],
                "tokens": tokenize(combined),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            invalidate(business_id)
            return {"ok": True, "result": {"question": q}, "action": atype}

        if atype == "list_knowledge":
            items = await db.knowledge_chunks.find({"business_id": business_id}, {"_id": 0, "id": 1, "source_title": 1, "source": 1}).limit(30).to_list(30)
            return {"ok": True, "result": {"items": items}, "action": atype}

        if atype == "delete_knowledge":
            match = (action.get("match") or "").strip()
            if not match:
                return {"ok": False, "error": "match keyword required", "action": atype}
            # match against source_title (case-insensitive) or text
            q = {"business_id": business_id, "$or": [
                {"source_title": {"$regex": re.escape(match), "$options": "i"}},
                {"text": {"$regex": re.escape(match), "$options": "i"}},
            ]}
            found = await db.knowledge_chunks.count_documents(q)
            if found == 0:
                return {"ok": False, "error": f"No knowledge matched '{match}'", "action": atype}
            res = await db.knowledge_chunks.delete_many(q)
            invalidate(business_id)
            return {"ok": True, "result": {"deleted": res.deleted_count, "match": match}, "action": atype}

        if atype == "update_appointment_settings":
            fields = action.get("fields") or {}
            valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
            services = fields.get("services")
            if not isinstance(services, list):
                services = None
            working_hours = fields.get("working_hours")
            hours = None
            if isinstance(working_hours, dict):
                hours = {d: working_hours.get(d) for d in valid_days}
            settings = {
                "enabled": bool(fields.get("enabled", False)),
                "services": [
                    {"name": str(s.get("name", "")).strip()[:80],
                     "duration_minutes": max(5, min(480, int(s.get("duration_minutes", 30))))}
                    for s in (services or []) if str(s.get("name", "")).strip()
                ][:30],
                "working_hours": hours or {d: None for d in valid_days},
                "slot_interval_minutes": max(5, min(240, int(fields.get("slot_interval_minutes", 30)))),
            }
            await db.businesses.update_one({"business_id": business_id}, {"$set": {"appointment_settings": settings}})
            return {"ok": True, "result": settings, "action": atype}

        if atype == "list_appointments":
            items = await db.appointments.find(
                {"business_id": business_id, "status": "confirmed"}, {"_id": 0}
            ).sort("start_time", 1).limit(50).to_list(50)
            return {"ok": True, "result": {"items": items}, "action": atype}

        if atype == "update_quick_facts":
            from datetime import datetime, timezone
            from freshness import touch as touch_knowledge
            fields = action.get("fields") or {}
            biz = await db.businesses.find_one({"business_id": business_id}, {"_id": 0, "quick_facts": 1})
            current = (biz or {}).get("quick_facts") or {}
            allowed = {"hours_note", "special_or_promo", "announcement"}
            updated = {**current}
            for k in allowed:
                if k in fields and fields[k] is not None:
                    updated[k] = str(fields[k])[:300]
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.businesses.update_one({"business_id": business_id}, {"$set": {"quick_facts": updated}})
            await touch_knowledge(business_id)
            return {"ok": True, "result": updated, "action": atype}

        return {"ok": False, "error": f"Unknown action type: {atype}", "action": atype}
    except Exception as e:
        return {"ok": False, "error": str(e), "action": action.get("type")}
