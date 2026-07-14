"""Audit receipts for owner-operated growth workflows."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db

DEFAULT_RECEIPT_LOG = "data/provider_growth_receipts.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def write_receipt(
    receipt_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    db_path: str = DEFAULT_DB_PATH,
    receipt_log: str = DEFAULT_RECEIPT_LOG,
) -> dict[str, Any]:
    """Persist a JSON receipt to SQLite and JSONL."""
    init_db(db_path)
    enriched = {
        "receipt_type": receipt_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "created_at": utc_now(),
        "payload": payload,
    }
    payload_hash = sha256_payload(enriched)
    enriched["payload_hash"] = payload_hash

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO receipts(receipt_type, entity_type, entity_id, payload_hash, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (receipt_type, entity_type, entity_id, payload_hash, stable_json(enriched)),
        )
        conn.commit()

    log_path = Path(receipt_log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n")
    return enriched
