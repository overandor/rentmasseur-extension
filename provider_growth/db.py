"""SQLite schema and helpers for the provider growth CRM."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = "data/provider_growth.sqlite3"

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS visitors (
        visitor_key TEXT PRIMARY KEY,
        display_name TEXT,
        profile_url TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        visit_count INTEGER NOT NULL DEFAULT 1,
        lead_score INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'new',
        do_not_contact INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS visitor_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_key TEXT NOT NULL,
        event_type TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual',
        event_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(visitor_key) REFERENCES visitors(visitor_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS message_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_key TEXT NOT NULL,
        template_name TEXT NOT NULL,
        body TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT 'platform',
        status TEXT NOT NULL DEFAULT 'draft',
        approval_required INTEGER NOT NULL DEFAULT 1,
        approved_at TEXT,
        sent_at TEXT,
        skipped_reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(visitor_key) REFERENCES visitors(visitor_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_key TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT 'imessage',
        client_handle_hash TEXT,
        last_inbound_at TEXT,
        last_outbound_at TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        interest_stage TEXT NOT NULL DEFAULT 'new',
        revenue_stage TEXT NOT NULL DEFAULT 'unknown',
        do_not_contact INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(visitor_key) REFERENCES visitors(visitor_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        body_hash TEXT NOT NULL,
        body_preview TEXT NOT NULL DEFAULT '',
        event_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conversation_id) REFERENCES client_conversations(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        field_name TEXT NOT NULL,
        label TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        content TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        activated_at TEXT,
        retired_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metrics_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_at TEXT NOT NULL,
        profile_version_label TEXT,
        profile_views INTEGER NOT NULL DEFAULT 0,
        repeat_visitors INTEGER NOT NULL DEFAULT 0,
        contact_actions INTEGER NOT NULL DEFAULT 0,
        inbound_messages INTEGER NOT NULL DEFAULT 0,
        booking_requests INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_visitor_events_key_time
    ON visitor_events(visitor_key, event_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_message_drafts_key_status
    ON message_drafts(visitor_key, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_profile_versions_label
    ON profile_versions(label)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversations_key_status
    ON client_conversations(visitor_key, status)
    """,
)


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
        conn.commit()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]
