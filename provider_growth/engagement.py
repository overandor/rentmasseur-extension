"""Manual engagement records for authorized account operations.

All records are operator-entered or imported from sources the operator is
authorized to use. This module does not collect hidden data or perform outbound
actions.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_key(identifier: str) -> str:
    return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()[:24]


def score_record(repeat_count: int = 1, recent: bool = True, cooldown: bool = False, blocked: bool = False) -> int:
    score = 0
    if repeat_count >= 2:
        score += 3
    if repeat_count >= 3:
        score += 2
    if recent:
        score += 2
    if cooldown:
        score -= 5
    if blocked:
        score -= 100
    return score


def upsert_record(identifier: str, display_name: str | None = None, source: str = "manual", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now()
    key = record_key(identifier)
    with connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM visitors WHERE visitor_key = ?", (key,)).fetchone()
        if existing:
            count = int(existing["visit_count"]) + 1
            score = score_record(count, recent=True, blocked=bool(existing["do_not_contact"]))
            conn.execute(
                "UPDATE visitors SET display_name = COALESCE(?, display_name), last_seen = ?, visit_count = ?, lead_score = ?, updated_at = CURRENT_TIMESTAMP WHERE visitor_key = ?",
                (display_name, now, count, score, key),
            )
        else:
            count = 1
            score = score_record(count, recent=True)
            conn.execute(
                "INSERT INTO visitors(visitor_key, display_name, profile_url, first_seen, last_seen, visit_count, lead_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, display_name, identifier, now, now, count, score),
            )
        conn.execute(
            "INSERT INTO visitor_events(visitor_key, event_type, source, event_at, metadata_json) VALUES (?, ?, ?, ?, '{}')",
            (key, "manual_record", source, now),
        )
        conn.commit()
    receipt = write_receipt("engagement_record", "record", key, {"source": source, "at": now}, db_path=db_path)
    return {"record_key": key, "repeat_count": count, "score": score, "receipt_hash": receipt["payload_hash"]}


def list_priority_records(min_score: int = 3, limit: int = 25, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT visitor_key AS record_key, display_name, last_seen, visit_count AS repeat_count, lead_score AS score, status FROM visitors WHERE lead_score >= ? AND do_not_contact = 0 ORDER BY lead_score DESC, last_seen DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
    return rows_to_dicts(rows)
