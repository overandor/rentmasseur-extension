"""Policy gate for provider growth operations.

The policy gate decides whether an approved draft may be exported for manual
handoff. It never sends messages. It only returns allow/block decisions with
reasons and receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db
from .receipts import write_receipt


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    decision: str
    reason: str
    next_action_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": self.decision,
            "reason": self.reason,
            "next_action_at": self.next_action_at,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_policy(db_path: str = DEFAULT_DB_PATH) -> dict[str, str]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM policy_rules").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_policy(key: str, value: str, description: str = "", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO policy_rules(key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, description=excluded.description, updated_at=CURRENT_TIMESTAMP
            """,
            (key, value, description),
        )
        conn.commit()
    receipt = write_receipt("policy_updated", "policy", key, {"key": key, "value": value, "description": description}, db_path=db_path)
    return {"key": key, "value": value, "receipt_hash": receipt["payload_hash"]}


def evaluate_draft(draft_id: int, db_path: str = DEFAULT_DB_PATH) -> PolicyDecision:
    """Return whether a draft is allowed to enter the manual handoff outbox."""
    init_db(db_path)
    policy = get_policy(db_path)
    with connect(db_path) as conn:
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            return PolicyDecision(False, "blocked", "draft_not_found")
        record = conn.execute("SELECT * FROM visitors WHERE visitor_key = ?", (draft["visitor_key"],)).fetchone()
        if not record:
            return PolicyDecision(False, "blocked", "record_not_found")
        conversation = conn.execute(
            "SELECT * FROM client_conversations WHERE visitor_key = ? ORDER BY updated_at DESC LIMIT 1",
            (draft["visitor_key"],),
        ).fetchone()

    if bool(record["do_not_contact"]):
        return PolicyDecision(False, "blocked", "record_marked_do_not_contact")
    if conversation and bool(conversation["do_not_contact"]):
        return PolicyDecision(False, "blocked", "conversation_marked_do_not_contact")
    if policy.get("manual_approval_required", "true").lower() == "true" and draft["status"] != "approved":
        return PolicyDecision(False, "needs_approval", "draft_requires_human_approval")
    if draft["status"] in {"exported", "sent", "skipped"}:
        return PolicyDecision(False, "blocked", f"draft_already_{draft['status']}")

    # This is intentionally conservative: quiet hours only affect handoff timing,
    # not content generation. Real timezone scheduling belongs in a later adapter.
    now_hour = datetime.now().hour
    start = int(policy.get("quiet_hours_start", "21"))
    end = int(policy.get("quiet_hours_end", "8"))
    if start > end and (now_hour >= start or now_hour < end):
        return PolicyDecision(False, "defer", "quiet_hours_active")

    return PolicyDecision(True, "allowed", "approved_for_manual_handoff")


def evaluate_and_receipt(draft_id: int, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    decision = evaluate_draft(draft_id, db_path=db_path)
    receipt = write_receipt("policy_decision", "draft", str(draft_id), decision.to_dict(), db_path=db_path)
    out = decision.to_dict()
    out["receipt_hash"] = receipt["payload_hash"]
    return out
