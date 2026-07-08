"""Manual outbox state machine.

The outbox is a queue of approved drafts ready for human review and local
handoff. It does not send messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .policy import evaluate_draft
from .receipts import write_receipt


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def enqueue_draft(draft_id: int, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    decision = evaluate_draft(draft_id, db_path=db_path)
    with connect(db_path) as conn:
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            raise ValueError(f"draft not found: {draft_id}")
        cur = conn.execute(
            """
            INSERT INTO outbox_items(draft_id, visitor_key, channel, state, policy_decision, policy_reason, next_action_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                draft["visitor_key"],
                draft["channel"],
                "ready" if decision.allowed else "blocked",
                decision.decision,
                decision.reason,
                decision.next_action_at,
            ),
        )
        outbox_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("outbox_enqueued", "outbox", str(outbox_id), {"draft_id": draft_id, "decision": decision.to_dict()}, db_path=db_path)
    return {"outbox_id": outbox_id, "state": "ready" if decision.allowed else "blocked", "policy": decision.to_dict(), "receipt_hash": receipt["payload_hash"]}


def export_ready_item(outbox_id: int, output_dir: str = "data/manual_outbox", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        item = conn.execute("SELECT * FROM outbox_items WHERE id = ?", (outbox_id,)).fetchone()
        if not item:
            raise ValueError(f"outbox item not found: {outbox_id}")
        if item["state"] != "ready":
            raise ValueError(f"outbox item must be ready, got {item['state']}")
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (item["draft_id"],)).fetchone()
        if not draft:
            raise ValueError("linked draft not found")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"outbox_{outbox_id}_draft_{item['draft_id']}.txt"
        path.write_text(draft["body"], encoding="utf-8")
        conn.execute(
            "UPDATE outbox_items SET state = 'exported', exported_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(path), outbox_id),
        )
        conn.execute(
            "UPDATE message_drafts SET status = 'exported' WHERE id = ?",
            (item["draft_id"],),
        )
        conn.commit()
    receipt = write_receipt("outbox_exported", "outbox", str(outbox_id), {"path": str(path)}, db_path=db_path)
    return {"outbox_id": outbox_id, "path": str(path), "receipt_hash": receipt["payload_hash"]}


def mark_completed(outbox_id: int, outcome: str = "manual_completed", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    if outcome not in {"manual_completed", "skipped", "failed"}:
        raise ValueError("outcome must be manual_completed, skipped, or failed")
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE outbox_items SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (outcome, outbox_id))
        conn.commit()
    receipt = write_receipt("outbox_completed", "outbox", str(outbox_id), {"outcome": outcome, "at": utc_now()}, db_path=db_path)
    return {"outbox_id": outbox_id, "state": outcome, "receipt_hash": receipt["payload_hash"]}


def list_outbox(state: str | None = None, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        if state:
            rows = conn.execute("SELECT * FROM outbox_items WHERE state = ? ORDER BY created_at DESC", (state,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM outbox_items ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)
