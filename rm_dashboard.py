#!/usr/bin/env python3
"""
RM Live Dashboard — Real-time RentMasseur operations dashboard.

Shows:
  - Current live bio (fetched from RM or cached)
  - Visitor count + timeline from engagement DB
  - Top visitors by visit count
  - Message history and status
  - Bio experiment results (which bio got more visitors)
  - Ollama bio candidates with scores
  - iMessage recent conversations

Usage:
  python3 rm_dashboard.py
  python3 rm_dashboard.py --port 8080 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

BASE_DIR = Path(__file__).parent
ENGAGEMENT_DB = BASE_DIR / "artifacts" / "engagement" / "engagement.db"
BIO_CACHE = BASE_DIR / "artifacts" / "engagement" / "current_bio.json"
BIO_EXPERIMENTS = BASE_DIR / "artifacts" / "engagement" / "bio_experiments.db"
IMESSAGE_DB = Path.home() / "Library" / "Messages" / "chat.db"

app = FastAPI(title="RM Live Dashboard", docs_url="/api/docs")


def get_engagement_conn() -> sqlite3.Connection:
    if not ENGAGEMENT_DB.exists():
        return None
    conn = sqlite3.connect(str(ENGAGEMENT_DB))
    conn.row_factory = sqlite3.Row
    return conn


def get_bio_experiments_conn() -> sqlite3.Connection:
    if not BIO_EXPERIMENTS.exists():
        return None
    conn = sqlite3.connect(str(BIO_EXPERIMENTS))
    conn.row_factory = sqlite3.Row
    return conn


def load_current_bio() -> dict:
    if BIO_CACHE.exists():
        try:
            return json.loads(BIO_CACHE.read_text())
        except Exception:
            pass
    return {"bio": "(not fetched yet)", "fetched_at": None, "char_count": 0}


def get_visitor_stats() -> dict:
    conn = get_engagement_conn()
    if not conn:
        return {"total": 0, "repeat_3plus": 0, "messaged": 0, "top_visitors": []}

    total = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    repeat_3 = conn.execute("SELECT COUNT(*) FROM visitors WHERE visit_count >= 3").fetchone()[0]
    repeat_2 = conn.execute("SELECT COUNT(*) FROM visitors WHERE visit_count >= 2").fetchone()[0]
    messaged = conn.execute("SELECT COUNT(*) FROM visitors WHERE message_count > 0").fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM visit_log").fetchone()[0]
    msgs_sent = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]

    top = conn.execute(
        "SELECT username, visit_count, last_online, last_seen, last_messaged, message_count "
        "FROM visitors ORDER BY visit_count DESC LIMIT 20"
    ).fetchall()

    conn.close()
    return {
        "total": total,
        "repeat_3plus": repeat_3,
        "repeat_2plus": repeat_2,
        "messaged": messaged,
        "visit_events": events,
        "messages_sent": msgs_sent,
        "top_visitors": [dict(r) for r in top],
    }


def get_recent_events(limit: int = 50) -> list:
    conn = get_engagement_conn()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT username, session_id, visited_at, status, content_hash "
            "FROM visit_log ORDER BY visited_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def get_message_history(limit: int = 20) -> list:
    conn = get_engagement_conn()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT username, sent_at, message_text, status, template_index "
            "FROM message_log ORDER BY sent_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def get_bio_experiments() -> list:
    conn = get_bio_experiments_conn()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT id, bio_text, model, deployed_at, removed_at, visitors_during, "
            "contact_clicks_during, score, status "
            "FROM bio_experiments ORDER BY deployed_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def get_imessage_recent(limit: int = 10) -> list:
    if not IMESSAGE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(IMESSAGE_DB))
        conn.row_factory = sqlite3.Row
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
        results = []
        for r in rows:
            d = dict(r)
            # Convert Apple epoch to ISO
            apple_epoch = d.get("date", 0)
            if apple_epoch:
                try:
                    dt = datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp() + apple_epoch / 1e9
                    d["date_iso"] = datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
                except Exception:
                    d["date_iso"] = str(apple_epoch)
            results.append(d)
        return results
    except Exception:
        return []


def get_imessage_conversations(limit: int = 20) -> list:
    if not IMESSAGE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(IMESSAGE_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                handle.id as contact,
                COUNT(*) as msg_count,
                MAX(message.date) as last_msg_date,
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
            apple_epoch = d.get("last_msg_date", 0)
            if apple_epoch:
                try:
                    dt = datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp() + apple_epoch / 1e9
                    d["last_msg_iso"] = datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
                except Exception:
                    d["last_msg_iso"] = str(apple_epoch)
            results.append(d)
        return results
    except Exception:
        return []


@app.get("/", response_class=HTMLResponse)
async def dashboard_html():
    bio = load_current_bio()
    visitors = get_visitor_stats()
    events = get_recent_events(30)
    messages = get_message_history(20)
    experiments = get_bio_experiments()
    imessage_convs = get_imessage_conversations(15)

    visitor_rows = "".join([
        f"<tr><td>{v['username']}</td><td>{v['visit_count']}</td>"
        f"<td>{v.get('last_online') or '—'}</td>"
        f"<td>{v.get('last_messaged')[:19] if v.get('last_messaged') else 'never'}</td>"
        f"<td>{v.get('message_count', 0)}</td></tr>"
        for v in visitors.get("top_visitors", [])[:15]
    ])

    event_rows = "".join([
        f"<tr><td>{(e.get('visited_at') or '?')[:19]}</td><td>{e.get('username')}</td>"
        f"<td>{e.get('status')}</td></tr>"
        for e in events[:20]
    ]) if events else "<tr><td colspan='3'>No visit events logged yet</td></tr>"

    msg_rows = "".join([
        f"<tr><td>{(m.get('sent_at') or '?')[:19]}</td><td>{m.get('username')}</td>"
        f"<td>{m.get('status')}</td><td>{(m.get('message_text') or '')[:60]}...</td></tr>"
        for m in messages
    ]) if messages else "<tr><td colspan='4'>No messages sent yet</td></tr>"

    exp_rows = "".join([
        f"<tr><td>{(e.get('deployed_at') or '—')[:19]}</td>"
        f"<td>{(e.get('bio_text') or '')[:80]}...</td>"
        f"<td>{e.get('model', '?')}</td>"
        f"<td>{e.get('visitors_during', 0)}</td>"
        f"<td>{e.get('score', '—')}</td>"
        f"<td>{e.get('status', '?')}</td></tr>"
        for e in experiments
    ]) if experiments else "<tr><td colspan='6'>No bio experiments yet</td></tr>"

    imessage_rows = "".join([
        f"<tr><td>{c.get('contact', '?')}</td>"
        f"<td>{c.get('msg_count', 0)}</td>"
        f"<td>{c.get('sent_by_me', 0)}/{c.get('sent_by_them', 0)}</td>"
        f"<td>{(c.get('last_msg_iso') or '—')[:19]}</td></tr>"
        for c in imessage_convs
    ]) if imessage_convs else "<tr><td colspan='4'>iMessage DB not accessible</td></tr>"

    bio_text = (bio.get("bio") or "(not fetched)")
    bio_display = bio_text[:500].replace("\n", "<br>") if bio_text else "(empty)"

    return f"""<!DOCTYPE html>
<html>
<head>
<title>RentMasseur Live Dashboard</title>
<meta http-equiv="refresh" content="30">
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #58a6ff; margin: 0 0 10px 0; }}
h2 {{ color: #79c0ff; margin-top: 30px; font-size: 18px; }}
.subtitle {{ color: #8b949e; font-size: 13px; margin-bottom: 20px; }}
.stats {{ display: flex; gap: 16px; margin: 20px 0; flex-wrap: wrap; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 24px; text-align: center; min-width: 120px; }}
.stat .num {{ font-size: 28px; font-weight: bold; color: #58a6ff; }}
.stat .label {{ font-size: 11px; color: #8b949e; margin-top: 4px; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.panel {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; overflow-x: auto; }}
.bio-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 10px 0; white-space: pre-wrap; font-size: 14px; line-height: 1.5; max-height: 300px; overflow-y: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; color: #8b949e; padding: 8px 6px; border-bottom: 1px solid #30363d; }}
td {{ padding: 6px; border-bottom: 1px solid #21262d; }}
tr:hover {{ background: #1c2128; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; }}
.badge-ok {{ background: #1a7f37; color: #fff; }}
.badge-fail {{ background: #da3633; color: #fff; }}
.badge-pending {{ background: #d29922; color: #000; }}
a {{ color: #58a6ff; }}
.refresh-note {{ color: #8b949e; font-size: 11px; margin-top: 10px; }}
</style>
</head>
<body>
<h1>RentMasseur Live Dashboard</h1>
<div class="subtitle">Auto-refreshing every 30s | {datetime.now(timezone.utc).isoformat()[:19]}</div>

<div class="stats">
<div class="stat"><div class="num">{visitors.get('total', 0)}</div><div class="label">Total Visitors</div></div>
<div class="stat"><div class="num">{visitors.get('repeat_3plus', 0)}</div><div class="label">3+ Visits</div></div>
<div class="stat"><div class="num">{visitors.get('repeat_2plus', 0)}</div><div class="label">2+ Visits</div></div>
<div class="stat"><div class="num">{visitors.get('messages_sent', 0)}</div><div class="label">Messages Sent</div></div>
<div class="stat"><div class="num">{visitors.get('messaged', 0)}</div><div class="label">Visitors Messaged</div></div>
<div class="stat"><div class="num">{len(experiments)}</div><div class="label">Bio Experiments</div></div>
</div>

<h2>Current Live Bio</h2>
<div class="bio-box">{bio_display}</div>
<div class="subtitle">Fetched: {bio.get('fetched_at', 'never')[:19] if bio.get('fetched_at') else 'never'} | {bio.get('char_count', 0)} chars</div>

<div class="grid">
<div class="panel">
<h2>Top Visitors (by visit count)</h2>
<table>
<tr><th>Username</th><th>Visits</th><th>Last Online</th><th>Last Messaged</th><th>Msgs</th></tr>
{visitor_rows}
</table>
</div>

<div class="panel">
<h2>Recent Visit Events</h2>
<table>
<tr><th>Time</th><th>Visitor</th><th>Status</th></tr>
{event_rows}
</table>
</div>

<div class="panel">
<h2>Message History</h2>
<table>
<tr><th>Sent At</th><th>To</th><th>Status</th><th>Preview</th></tr>
{msg_rows}
</table>
</div>

<div class="panel">
<h2>Bio Experiments (Ollama)</h2>
<table>
<tr><th>Deployed</th><th>Bio Preview</th><th>Model</th><th>Visitors</th><th>Score</th><th>Status</th></tr>
{exp_rows}
</table>
</div>
</div>

<h2>iMessage Conversations</h2>
<div class="panel">
<table>
<tr><th>Contact</th><th>Total Msgs</th><th>Sent/Received</th><th>Last Message</th></tr>
{imessage_rows}
</table>
</div>

<div class="refresh-note">Auto-refresh: 30s | <a href="/api/stats">JSON API</a> | <a href="/api/visitors">Visitors JSON</a> | <a href="/api/bio">Bio JSON</a></div>
</body>
</html>"""


@app.get("/api/stats")
async def api_stats():
    return JSONResponse({
        "bio": load_current_bio(),
        "visitors": get_visitor_stats(),
        "recent_events": get_recent_events(50),
        "messages": get_message_history(50),
        "bio_experiments": get_bio_experiments(),
        "imessage_conversations": get_imessage_conversations(20),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/visitors")
async def api_visitors():
    return JSONResponse(get_visitor_stats())


@app.get("/api/bio")
async def api_bio():
    return JSONResponse(load_current_bio())


@app.get("/api/messages")
async def api_messages():
    return JSONResponse(get_message_history(100))


@app.get("/api/experiments")
async def api_experiments():
    return JSONResponse(get_bio_experiments())


@app.get("/api/imessage")
async def api_imessage():
    return JSONResponse({
        "conversations": get_imessage_conversations(50),
        "recent_messages": get_imessage_recent(50),
    })


def main():
    parser = argparse.ArgumentParser(description="RM Live Dashboard")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"RM Dashboard: http://{args.host}:{args.port}")
    print(f"  Engagement DB: {ENGAGEMENT_DB} ({'exists' if ENGAGEMENT_DB.exists() else 'missing'})")
    print(f"  Bio cache: {BIO_CACHE} ({'exists' if BIO_CACHE.exists() else 'missing'})")
    print(f"  iMessage DB: {IMESSAGE_DB} ({'exists' if IMESSAGE_DB.exists() else 'missing'})")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
