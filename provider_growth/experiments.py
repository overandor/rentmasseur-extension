"""Simple conversion experiment metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def add_snapshot(
    profile_version_label: str | None = None,
    profile_views: int = 0,
    repeat_visitors: int = 0,
    contact_actions: int = 0,
    inbound_messages: int = 0,
    booking_requests: int = 0,
    metadata: dict[str, Any] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO metrics_snapshots(snapshot_at, profile_version_label, profile_views, repeat_visitors, contact_actions, inbound_messages, booking_requests, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, profile_version_label, profile_views, repeat_visitors, contact_actions, inbound_messages, booking_requests, json.dumps(metadata or {}, sort_keys=True)),
        )
        snapshot_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("metrics_snapshot", "metrics_snapshot", str(snapshot_id), {"snapshot_at": now, "profile_version_label": profile_version_label}, db_path=db_path)
    return {"snapshot_id": snapshot_id, "snapshot_at": now, "receipt_hash": receipt["payload_hash"]}


def summarize_by_version(db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              COALESCE(profile_version_label, 'unlabeled') AS profile_version_label,
              COUNT(*) AS snapshots,
              SUM(profile_views) AS profile_views,
              SUM(repeat_visitors) AS repeat_visitors,
              SUM(contact_actions) AS contact_actions,
              SUM(inbound_messages) AS inbound_messages,
              SUM(booking_requests) AS booking_requests
            FROM metrics_snapshots
            GROUP BY COALESCE(profile_version_label, 'unlabeled')
            ORDER BY booking_requests DESC, inbound_messages DESC, contact_actions DESC
            """
        ).fetchall()
    out = rows_to_dicts(rows)
    for row in out:
        views = row.get("profile_views") or 0
        contacts = row.get("contact_actions") or 0
        bookings = row.get("booking_requests") or 0
        row["contact_rate"] = round(contacts / views, 4) if views else 0.0
        row["booking_rate"] = round(bookings / views, 4) if views else 0.0
    return out
