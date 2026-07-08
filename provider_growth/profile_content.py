"""Profile content versioning and experiment labels."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt

VALID_FIELDS = {"bio", "blog", "interview", "availability_note", "headline"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def add_version(field_name: str, label: str, content: str, reason: str = "", status: str = "draft", db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    if field_name not in VALID_FIELDS:
        raise ValueError(f"field_name must be one of {sorted(VALID_FIELDS)}")
    init_db(db_path)
    h = content_hash(content)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO profile_versions(field_name, label, content_hash, content, reason, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (field_name, label, h, content, reason, status),
        )
        version_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("profile_version_created", "profile_version", str(version_id), {"field_name": field_name, "label": label, "content_hash": h, "reason": reason, "status": status}, db_path=db_path)
    return {"version_id": version_id, "field_name": field_name, "label": label, "content_hash": h, "status": status, "receipt_hash": receipt["payload_hash"]}


def activate_version(version_id: int, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    now = utc_now()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM profile_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            raise ValueError(f"version not found: {version_id}")
        conn.execute("UPDATE profile_versions SET status = 'retired', retired_at = ? WHERE field_name = ? AND status = 'active'", (now, row["field_name"]))
        conn.execute("UPDATE profile_versions SET status = 'active', activated_at = ? WHERE id = ?", (now, version_id))
        conn.commit()
    receipt = write_receipt("profile_version_activated", "profile_version", str(version_id), {"activated_at": now, "field_name": row["field_name"], "label": row["label"]}, db_path=db_path)
    return {"version_id": version_id, "status": "active", "activated_at": now, "receipt_hash": receipt["payload_hash"]}


def list_versions(field_name: str | None = None, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        if field_name:
            rows = conn.execute("SELECT * FROM profile_versions WHERE field_name = ? ORDER BY created_at DESC", (field_name,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM profile_versions ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)
