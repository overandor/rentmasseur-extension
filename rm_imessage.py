#!/usr/bin/env python3
"""
RM iMessage Bridge — Reads iMessage conversations and feeds them into
the reply drafting pipeline.

Reads from ~/Library/Messages/chat.db on macOS to:
  1. Extract recent conversations with clients
  2. Identify RM-related contacts (by username, phone, or content)
  3. Match iMessage contacts to RM visitors
  4. Generate reply drafts using local Ollama
  5. Store everything in engagement DB for the dashboard

Usage:
  python3 rm_imessage.py --sync           # Sync recent messages to DB
  python3 rm_imessage.py --conversations   # List all conversations
  python3 rm_imessage.py --draft --contact "+1234567890"  # Draft reply
  python3 rm_imessage.py --match-visitors  # Match iMessage contacts to RM visitors
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
ARTIFACTS = BASE_DIR / "artifacts" / "engagement"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
ENGAGEMENT_DB = ARTIFACTS / "engagement.db"
IMESSAGE_DB = Path.home() / "Library" / "Messages" / "chat.db"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Keywords that suggest RM-related conversations
RM_KEYWORDS = [
    "massage", "session", "booking", "appointment", "incall", "outcall",
    "manhattan", "nyc", "available", "schedule", "deep tissue", "swedish",
    "rentmasseur", "rm.com", "masseur",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str, level: str = "INFO"):
    print(f"[IMESSAGE] [{level}] {msg}")


def apple_epoch_to_iso(epoch_ns: int) -> str:
    """Convert Apple's Core Data timestamp (nanoseconds since 2001-01-01) to ISO."""
    try:
        unix_ts = datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp() + epoch_ns / 1e9
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
    except Exception:
        return str(epoch_ns)


def get_imessage_conn() -> Optional[sqlite3.Connection]:
    if not IMESSAGE_DB.exists():
        log(f"iMessage DB not found: {IMESSAGE_DB}", "ERROR")
        return None
    try:
        conn = sqlite3.connect(f"file:{IMESSAGE_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        log(f"Cannot open iMessage DB: {e}", "ERROR")
        return None


# ─── Conversation Extraction ─────────────────────────────────────────

def get_conversations(limit: int = 50) -> list:
    """Get all conversations with message counts and last message time."""
    conn = get_imessage_conn()
    if not conn:
        return []

    rows = conn.execute("""
        SELECT
            handle.id as contact,
            handle.service as service,
            COUNT(*) as msg_count,
            MAX(message.date) as last_msg_date,
            MIN(message.date) as first_msg_date,
            SUM(CASE WHEN message.is_from_me = 1 THEN 1 ELSE 0 END) as sent_by_me,
            SUM(CASE WHEN message.is_from_me = 0 THEN 1 ELSE 0 END) as sent_by_them
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.text IS NOT NULL
        GROUP BY handle.id
        ORDER BY last_msg_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d["last_msg_iso"] = apple_epoch_to_iso(d.get("last_msg_date", 0))
        d["first_msg_iso"] = apple_epoch_to_iso(d.get("first_msg_date", 0))
        # Check if RM-related
        d["is_rm_related"] = check_rm_related(d["contact"])
        results.append(d)
    return results


def get_conversation_messages(contact: str, limit: int = 50) -> list:
    """Get messages from a specific contact."""
    conn = get_imessage_conn()
    if not conn:
        return []

    rows = conn.execute("""
        SELECT
            message.ROWID as msg_id,
            message.text as text,
            message.date as date,
            message.is_from_me as is_from_me,
            handle.id as contact
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE handle.id = ? AND message.text IS NOT NULL
        ORDER BY message.date DESC
        LIMIT ?
    """, (contact, limit)).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d["date_iso"] = apple_epoch_to_iso(d.get("date", 0))
        results.append(d)
    return results


def check_rm_related(contact: str) -> bool:
    """Check if a contact identifier appears in the RM visitor DB."""
    if not ENGAGEMENT_DB.exists():
        return False
    try:
        conn = sqlite3.connect(str(ENGAGEMENT_DB))
        # Check if contact matches any visitor username
        row = conn.execute(
            "SELECT username FROM visitors WHERE username LIKE ? OR username LIKE ?",
            (f"%{contact}%", f"%{contact.replace('+', '')}%")
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def get_rm_related_conversations() -> list:
    """Get conversations that are likely RM-related (by keyword or contact match)."""
    convs = get_conversations(200)
    rm_convs = []

    for c in convs:
        if c.get("is_rm_related"):
            rm_convs.append(c)
            continue

        # Check message content for RM keywords
        messages = get_conversation_messages(c["contact"], limit=10)
        for msg in messages:
            text_lower = (msg.get("text") or "").lower()
            if any(kw in text_lower for kw in RM_KEYWORDS):
                c["is_rm_related"] = True
                c["matched_keyword"] = next(
                    (kw for kw in RM_KEYWORDS if kw in text_lower), None
                )
                break

        if c.get("is_rm_related"):
            rm_convs.append(c)

    return rm_convs


# ─── Sync to Engagement DB ───────────────────────────────────────────

def init_imessage_table():
    if not ENGAGEMENT_DB.exists():
        return
    conn = sqlite3.connect(str(ENGAGEMENT_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS imessage_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact TEXT NOT NULL,
            msg_id INTEGER,
            text TEXT,
            date_iso TEXT,
            is_from_me INTEGER,
            synced_at TEXT NOT NULL,
            is_rm_related INTEGER DEFAULT 0,
            matched_visitor TEXT,
            UNIQUE(msg_id)
        )
    """)
    conn.commit()
    conn.close()


def sync_messages(limit: int = 500):
    """Sync recent iMessages to the engagement DB."""
    init_imessage_table()

    conn = get_imessage_conn()
    if not conn:
        return 0

    rows = conn.execute("""
        SELECT
            message.ROWID as msg_id,
            message.text as text,
            message.date as date,
            message.is_from_me as is_from_me,
            handle.id as contact
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.text IS NOT NULL
        ORDER BY message.date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    eng_conn = sqlite3.connect(str(ENGAGEMENT_DB))
    synced = 0
    for r in rows:
        d = dict(r)
        date_iso = apple_epoch_to_iso(d.get("date", 0))
        is_rm = 1 if check_rm_related(d["contact"]) else 0

        # Check message content for RM keywords
        text_lower = (d.get("text") or "").lower()
        matched_kw = None
        if not is_rm:
            for kw in RM_KEYWORDS:
                if kw in text_lower:
                    is_rm = 1
                    matched_kw = kw
                    break

        try:
            eng_conn.execute(
                "INSERT OR IGNORE INTO imessage_sync "
                "(contact, msg_id, text, date_iso, is_from_me, synced_at, is_rm_related) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (d["contact"], d["msg_id"], d["text"], date_iso,
                 d["is_from_me"], now_iso(), is_rm)
            )
            synced += eng_conn.total_changes > 0
        except Exception:
            pass

    eng_conn.commit()

    # Count RM-related
    rm_count = eng_conn.execute(
        "SELECT COUNT(*) FROM imessage_sync WHERE is_rm_related=1"
    ).fetchone()[0]
    total_synced = eng_conn.execute("SELECT COUNT(*) FROM imessage_sync").fetchone()[0]
    eng_conn.close()

    log(f"Synced {len(rows)} messages ({synced} new). Total: {total_synced}, RM-related: {rm_count}")
    return synced


# ─── Reply Drafting with Ollama ──────────────────────────────────────

def draft_reply(contact: str, context_messages: int = 20) -> str:
    """Generate a reply draft for a contact using Ollama."""
    messages = get_conversation_messages(contact, limit=context_messages)
    if not messages:
        return "(no messages found for this contact)"

    # Build conversation context
    messages.reverse()  # chronological order
    conversation = ""
    for msg in messages:
        sender = "Me" if msg["is_from_me"] else "Client"
        conversation += f"{sender}: {msg['text']}\n"

    prompt = f"""You are a professional massage therapist on RentMasseur.com responding to a client via iMessage.
Based on the conversation below, draft a short, friendly, professional reply.

Conversation:
{conversation}

Rules:
- Keep it under 200 characters
- Be warm but professional
- If they're asking about booking, mention availability
- If they're asking about location, mention Manhattan incall
- Do not use emoji
- Write only the reply message, nothing else

Reply:"""

    import requests
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 150}
        }, timeout=60)
        resp.raise_for_status()
        draft = resp.json().get("response", "").strip()
        return draft
    except Exception as e:
        log(f"Ollama error: {e}", "ERROR")
        return f"(draft generation failed: {e})"


# ─── Match Visitors to iMessage Contacts ─────────────────────────────

def match_visitors_to_contacts() -> list:
    """Try to match RM visitor usernames to iMessage contacts."""
    if not ENGAGEMENT_DB.exists():
        return []

    eng_conn = sqlite3.connect(str(ENGAGEMENT_DB))
    visitors = eng_conn.execute("SELECT username FROM visitors").fetchall()
    eng_conn.close()

    im_conn = get_imessage_conn()
    if not im_conn:
        return []

    # Get all iMessage contacts
    contacts = im_conn.execute("SELECT DISTINCT id FROM handle").fetchall()
    im_conn.close()

    matches = []
    visitor_names = [v[0].lower() for v in visitors]
    contact_list = [c[0] for c in contacts]

    for vname in visitor_names:
        for contact in contact_list:
            # Match by partial phone number or email
            contact_clean = contact.replace("+", "").replace("-", "").replace(" ", "").lower()
            if vname in contact_clean or contact_clean in vname:
                matches.append({"visitor": vname, "contact": contact})
            # Also check if contact email contains username
            elif "@" in contact and vname in contact.lower():
                matches.append({"visitor": vname, "contact": contact})

    log(f"Matched {len(matches)} visitors to iMessage contacts")
    return matches


# ─── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RM iMessage Bridge")
    parser.add_argument("--sync", action="store_true", help="Sync recent messages to DB")
    parser.add_argument("--conversations", action="store_true", help="List all conversations")
    parser.add_argument("--rm-conversations", action="store_true", help="List RM-related conversations only")
    parser.add_argument("--draft", action="store_true", help="Draft a reply for a contact")
    parser.add_argument("--contact", help="Contact ID for drafting")
    parser.add_argument("--match-visitors", action="store_true", help="Match visitors to iMessage contacts")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    args = parser.parse_args()

    if not IMESSAGE_DB.exists():
        log(f"iMessage DB not found: {IMESSAGE_DB}", "ERROR")
        log("This script only works on macOS with iMessage enabled.", "ERROR")
        sys.exit(1)

    if args.sync:
        sync_messages(limit=args.limit * 10)
        return

    if args.conversations:
        convs = get_conversations(args.limit)
        print(f"\n{'Contact':30s} {'Msgs':>5s} {'Sent':>5s} {'Recv':>5s} {'Last Message':20s} {'RM':>3s}")
        print("-" * 80)
        for c in convs:
            print(f"{c['contact']:30s} {c['msg_count']:5d} {c['sent_by_me']:5d} "
                  f"{c['sent_by_them']:5d} {c['last_msg_iso'][:19]:20s} {'✓' if c['is_rm_related'] else '—':3s}")
        return

    if args.rm_conversations:
        convs = get_rm_related_conversations()
        print(f"\nRM-related conversations ({len(convs)}):")
        for c in convs:
            print(f"\n  {c['contact']} ({c['msg_count']} msgs, last: {c['last_msg_iso'][:19]})")
            if c.get("matched_keyword"):
                print(f"    Matched keyword: {c['matched_keyword']}")
            # Show last 3 messages
            msgs = get_conversation_messages(c["contact"], limit=3)
            for m in reversed(msgs):
                sender = "Me" if m["is_from_me"] else "Them"
                print(f"    [{m['date_iso'][:19]}] {sender}: {m['text'][:80]}")
        return

    if args.draft:
        if not args.contact:
            log("--contact required for --draft", "ERROR")
            sys.exit(1)
        draft = draft_reply(args.contact)
        print(f"\nDraft reply for {args.contact}:")
        print(f"  \"{draft}\"")
        return

    if args.match_visitors:
        matches = match_visitors_to_contacts()
        if matches:
            print(f"\nVisitor → iMessage contact matches:")
            for m in matches:
                print(f"  {m['visitor']} → {m['contact']}")
        else:
            print("\nNo matches found")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
