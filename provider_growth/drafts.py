"""Manual draft queue.

Drafts are suggestions for human review. This module never transmits outbound
content. The operator must approve and perform any outbound action separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt

TEMPLATES: dict[str, str] = {
    "soft_checkin": "Hi {name}, thanks for checking in. I have a little availability coming up. Want me to send the current window?",
    "same_day": "Hi {name}, I may have same-day availability. Send me your preferred time window and I will confirm what is realistic.",
    "weekend": "Hi {name}, I am organizing the weekend schedule now. If you are considering a session, send your ideal day and time window.",
    "content_followup": "Hi {name}, I updated my profile notes with a little more detail. Happy to answer any question before you book.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def render_template(template_name: str, name: str = "there") -> str:
    if template_name not in TEMPLATES:
        raise ValueError(f"unknown template: {template_name}")
    return TEMPLATES[template_name].format(name=name or "there")


def create_draft(record_key: str, template_name: str, name: str = "there", channel: str = "manual", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    body = render_template(template_name, name=name)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO message_drafts(visitor_key, template_name, body, channel, status, approval_required)
            VALUES (?, ?, ?, ?, 'draft', 1)
            """,
            (record_key, template_name, body, channel),
        )
        draft_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("draft_created", "draft", str(draft_id), {"record_key": record_key, "template": template_name, "channel": channel}, db_path=db_path)
    return {"draft_id": draft_id, "body": body, "status": "draft", "approval_required": True, "receipt_hash": receipt["payload_hash"]}


def approve_draft(draft_id: int, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now()
    with connect(db_path) as conn:
        conn.execute("UPDATE message_drafts SET status = 'approved', approved_at = ? WHERE id = ? AND status = 'draft'", (now, draft_id))
        row = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.commit()
    receipt = write_receipt("draft_approved", "draft", str(draft_id), {"approved_at": now}, db_path=db_path)
    return {"draft": dict(row) if row else None, "receipt_hash": receipt["payload_hash"]}


def list_drafts(status: str = "draft", db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM message_drafts WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
    return rows_to_dicts(rows)
