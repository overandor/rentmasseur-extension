"""Revenue liquidity and funnel KPIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import DEFAULT_DB_PATH, connect, init_db, rows_to_dicts
from .receipts import write_receipt


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def add_revenue_event(
    event_type: str,
    amount_cents: int = 0,
    visitor_key: str | None = None,
    currency: str = "USD",
    source: str = "manual",
    notes: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    if event_type not in {"inquiry", "quote", "booking_request", "confirmed_booking", "completed_booking", "cancelled"}:
        raise ValueError("unsupported revenue event type")
    init_db(db_path)
    now = utc_now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO revenue_events(visitor_key, event_type, amount_cents, currency, event_at, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (visitor_key, event_type, amount_cents, currency, now, source, notes),
        )
        event_id = int(cur.lastrowid)
        conn.commit()
    receipt = write_receipt("revenue_event", "revenue_event", str(event_id), {"event_type": event_type, "amount_cents": amount_cents, "currency": currency, "at": now}, db_path=db_path)
    return {"event_id": event_id, "event_type": event_type, "amount_cents": amount_cents, "receipt_hash": receipt["payload_hash"]}


def revenue_summary(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        events = rows_to_dicts(conn.execute("SELECT * FROM revenue_events ORDER BY event_at DESC").fetchall())
        outbox = rows_to_dicts(conn.execute("SELECT state, COUNT(*) AS count FROM outbox_items GROUP BY state").fetchall())
        drafts = rows_to_dicts(conn.execute("SELECT status, COUNT(*) AS count FROM message_drafts GROUP BY status").fetchall())
        snapshots = rows_to_dicts(conn.execute("SELECT SUM(profile_views) AS views, SUM(contact_actions) AS contacts, SUM(inbound_messages) AS inbound, SUM(booking_requests) AS bookings FROM metrics_snapshots").fetchall())

    totals: dict[str, int] = {}
    amount_confirmed = 0
    amount_completed = 0
    for ev in events:
        totals[ev["event_type"]] = totals.get(ev["event_type"], 0) + 1
        if ev["event_type"] == "confirmed_booking":
            amount_confirmed += int(ev["amount_cents"])
        if ev["event_type"] == "completed_booking":
            amount_completed += int(ev["amount_cents"])

    snap = snapshots[0] if snapshots else {"views": 0, "contacts": 0, "inbound": 0, "bookings": 0}
    views = snap.get("views") or 0
    bookings = snap.get("bookings") or 0
    contacts = snap.get("contacts") or 0

    return {
        "events_by_type": totals,
        "confirmed_pipeline_usd": round(amount_confirmed / 100, 2),
        "completed_revenue_usd": round(amount_completed / 100, 2),
        "outbox_by_state": {row["state"]: row["count"] for row in outbox},
        "drafts_by_status": {row["status"]: row["count"] for row in drafts},
        "views": views,
        "contacts": contacts,
        "booking_requests": bookings,
        "contact_rate": round(contacts / views, 4) if views else 0.0,
        "booking_request_rate": round(bookings / views, 4) if views else 0.0,
    }
