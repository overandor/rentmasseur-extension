"""iMac manual relay helpers.

This module prepares reviewable local handoffs for the operator. It does not
transmit messages. Use it to copy approved drafts into the Mac workflow after
human review.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def handle_hash(handle: str) -> str:
    return hashlib.sha256(handle.strip().lower().encode("utf-8")).hexdigest()


def open_conversation_record(record_key: str, client_handle: str | None = None, channel: str = "imessage", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now()
    h = handle_hash(client_handle) if client_handle else None
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO client_conversations(visitor_key, channel, client_handle_hash, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (record_key, channel, h),
        )
        conversation_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("conversation_opened", "conversation", str(conversation_id), {"record_key": record_key, "channel": channel, "has_handle": bool(client_handle), "opened_at": now}, db_path=db_path)
    return {"conversation_id": conversation_id, "record_key": record_key, "channel": channel, "receipt_hash": receipt["payload_hash"]}


def log_conversation_event(conversation_id: int, direction: str, body: str, event_at: str | None = None, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    if direction not in {"inbound", "outbound", "note"}:
        raise ValueError("direction must be inbound, outbound, or note")
    init_db(db_path)
    now = event_at or utc_now()
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    preview = body[:120]
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO conversation_events(conversation_id, direction, body_hash, body_preview, event_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, direction, body_hash, preview, now),
        )
        if direction == "inbound":
            conn.execute("UPDATE client_conversations SET last_inbound_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (now, conversation_id))
        elif direction == "outbound":
            conn.execute("UPDATE client_conversations SET last_outbound_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (now, conversation_id))
        conn.commit()
    receipt = write_receipt("conversation_event", "conversation", str(conversation_id), {"direction": direction, "body_hash": body_hash, "event_at": now}, db_path=db_path)
    return {"conversation_id": conversation_id, "direction": direction, "body_hash": body_hash, "receipt_hash": receipt["payload_hash"]}


def export_manual_handoff(draft_id: int, output_dir: str = "data/imac_handoffs", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Export an approved draft as a local text file for manual Mac review."""
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise ValueError(f"draft not found: {draft_id}")
    if row["status"] != "approved":
        raise ValueError("draft must be approved before handoff export")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"draft_{draft_id}.txt"
    path.write_text(row["body"], encoding="utf-8")
    receipt = write_receipt("manual_handoff_exported", "draft", str(draft_id), {"path": str(path), "channel": row["channel"]}, db_path=db_path)
    return {"draft_id": draft_id, "path": str(path), "receipt_hash": receipt["payload_hash"]}


def list_conversations(status: str = "active", db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM client_conversations WHERE status = ? ORDER BY updated_at DESC", (status,)).fetchall()
    return rows_to_dicts(rows)
