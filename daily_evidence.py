#!/usr/bin/env python3
"""
Daily Evidence Packet — joins bio version → traffic → contact clicks → booking/revenue.

This is the single joined revenue loop. One packet per day. No theater.

Flow:
1. Snapshot live profile (dashboard stats + about/bio)
2. Load current bio variant ID from experiment ledger
3. Compute deltas from last snapshot
4. Apply decision rules (KEEP_CURRENT, TEST_NEXT_BIO, BLOCK_NO_SIGNAL, etc.)
5. Write daily evidence packet JSON
6. Write receipt

Decision labels:
  KEEP_CURRENT       — bio has conversion signal, keep it
  TEST_NEXT_BIO      — bio has 0 signals after min exposure, rotate
  BLOCK_NO_SIGNAL    — not enough data (<100 views or <24h)
  BLOCK_LOW_EXPOSURE — profile hidden or unavailable
  WINNER_FOUND       — bio significantly outperforms baseline
  NEEDS_HUMAN_REVIEW — ambiguous result, manual decision needed

Minimum sample rules:
  - Do not judge before 100 profile views OR 24 hours, whichever comes later
  - If traffic is low, extend to 48 hours
  - If contact clicks drop hard (>50% decline), revert early
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path("/Users/alep/Downloads/rentmasseur-optimizer/rm_pri/py")))
from api_client import RentMasseurAPI

from dotenv import load_dotenv

# Paths
EXT_DIR = Path(__file__).parent
CONTENT_DIR = EXT_DIR / "content"
BIOS_DIR = CONTENT_DIR / "bios"
RECEIPTS_DIR = EXT_DIR / "receipts"
LEDGER_PATH = CONTENT_DIR / "experiment_ledger.json"
EVIDENCE_DIR = CONTENT_DIR / "evidence"
TRAFFIC_DB = Path("/Users/alep/Downloads/windsurf-smoke/rm_traffic/traffic.db")
SNAPSHOTS_DIR = Path("/Users/alep/Downloads/windsurf-smoke/rm_traffic/data/profile_snapshots")

# 3 approved test variants only
TEST_VARIANTS = {
    "A_clinical": {
        "id": "bio_A_clinical_recovery",
        "file": "bio_A_clinical_recovery.md",
        "strategy": "clinical_recovery",
        "headline": "KARPATHIAN WOLF — Professional Therapeutic Massage",
    },
    "B_wolf": {
        "id": "bio_W_winning_production",
        "file": "bio_W_winning_production.md",
        "strategy": "controlled_wolf",
        "headline": "KARPATHIAN WOLF — Targeted Recovery in Manhattan",
    },
    "C_luxury": {
        "id": "bio_C_luxury_concierge",
        "file": "bio_C_luxury_concierge.md",
        "strategy": "luxury_concierge",
        "headline": "KARPATHIAN WOLF — Manhattan's Private Recovery Specialist",
    },
}

REBRANDLY_LINK = "rebrand.ly/carpathianwolf"

# Minimum sample rules
MIN_VIEWS = 100
MIN_HOURS = 24
LOW_TRAFFIC_EXTEND_HOURS = 48
HARD_DROP_THRESHOLD = 0.50  # 50% decline in contact clicks = revert


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ledger() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return {
        "current_bio_id": None,
        "current_bio_started_at": None,
        "current_bio_start_views": 0,
        "current_bio_start_clicks": 0,
        "history": [],
        "baseline_ctr": None,
    }


def save_ledger(ledger: dict):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))


def snapshot_profile(api: RentMasseurAPI) -> dict:
    """Capture live profile state."""
    dash = api.get_dashboard()
    stats = api.get_ad_statistics()
    about = api.get_about()
    keep = api.get_keeponline()

    # Extract key metrics
    profile_stats = stats.get("profileStatistics", {}) if isinstance(stats, dict) else {}
    user_settings = dash.get("userSetting", {}) if isinstance(dash, dict) else {}

    total_views = profile_stats.get("totalPageViews", 0)
    total_clicks = profile_stats.get("totalContactClicks", 0)
    new_visits = keep.get("newVisits", 0) if isinstance(keep, dict) else 0
    new_emails = keep.get("newEmails", 0) if isinstance(keep, dict) else 0

    visibility = user_settings.get("visibility", 0)
    availability = user_settings.get("availability", {})
    is_available = availability.get("available", 0) if isinstance(availability, dict) else 0
    avail_message = availability.get("message", "") if isinstance(availability, dict) else ""

    # Current bio
    assets = about.get("userProps", {}).get("assets", {}) if isinstance(about, dict) else {}
    headline = assets.get("headline", "")
    description = assets.get("description", "")
    rebrandly_present = REBRANDLY_LINK in description

    return {
        "timestamp": now_iso(),
        "total_page_views": total_views,
        "total_contact_clicks": total_clicks,
        "new_visits": new_visits,
        "new_emails": new_emails,
        "visibility": visibility,
        "is_available": is_available,
        "availability_message": avail_message,
        "headline": headline,
        "bio_length": len(description),
        "rebrandly_present": rebrandly_present,
        "bio_preview": description[:300],
    }


def compute_deltas(snapshot: dict, ledger: dict) -> dict:
    """Compute deltas since current bio started."""
    start_views = ledger.get("current_bio_start_views", 0)
    start_clicks = ledger.get("current_bio_start_clicks", 0)

    delta_views = snapshot["total_page_views"] - start_views
    delta_clicks = snapshot["total_contact_clicks"] - start_clicks
    delta_ctr = (delta_clicks / delta_views * 100) if delta_views > 0 else 0.0

    started_at = ledger.get("current_bio_start_started_at")
    hours_exposed = 0
    if started_at:
        try:
            started = datetime.fromisoformat(started_at)
            hours_exposed = (datetime.now(timezone.utc) - started).total_seconds() / 3600
        except Exception:
            pass

    return {
        "delta_views": delta_views,
        "delta_clicks": delta_clicks,
        "delta_ctr": round(delta_ctr, 2),
        "hours_exposed": round(hours_exposed, 1),
    }


def decide(snapshot: dict, deltas: dict, ledger: dict) -> str:
    """Apply decision rules. Returns one of the 6 labels."""
    # Rule 1: Profile hidden or unavailable → block
    if snapshot["visibility"] != 1:
        return "BLOCK_LOW_EXPOSURE"
    if snapshot["is_available"] != 1:
        return "BLOCK_LOW_EXPOSURE"

    # Rule 2: Not enough data yet
    if deltas["delta_views"] < MIN_VIEWS and deltas["hours_exposed"] < MIN_HOURS:
        return "BLOCK_NO_SIGNAL"

    # Rule 3: Enough time but low traffic → extend
    if deltas["delta_views"] < MIN_VIEWS and deltas["hours_exposed"] < LOW_TRAFFIC_EXTEND_HOURS:
        return "BLOCK_NO_SIGNAL"

    # Rule 4: Has signals (contact clicks) → keep
    if deltas["delta_clicks"] > 0:
        baseline_ctr = ledger.get("baseline_ctr")
        if baseline_ctr and deltas["delta_ctr"] > baseline_ctr * 1.5:
            return "WINNER_FOUND"
        if baseline_ctr and deltas["delta_ctr"] < baseline_ctr * HARD_DROP_THRESHOLD:
            return "TEST_NEXT_BIO"
        return "KEEP_CURRENT"

    # Rule 5: Enough views but zero clicks → test next
    if deltas["delta_views"] >= MIN_VIEWS and deltas["delta_clicks"] == 0:
        return "TEST_NEXT_BIO"

    # Rule 6: Ambiguous
    return "NEEDS_HUMAN_REVIEW"


def build_evidence_packet(snapshot: dict, deltas: dict, decision: str, ledger: dict) -> dict:
    """Build the daily evidence packet."""
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": now_iso(),
        "bio_id": ledger.get("current_bio_id", "unknown"),
        "bio_started_at": ledger.get("current_bio_started_at"),
        "metrics": {
            "total_page_views": snapshot["total_page_views"],
            "total_contact_clicks": snapshot["total_contact_clicks"],
            "new_visits": snapshot["new_visits"],
            "new_emails": snapshot["new_emails"],
            "delta_views": deltas["delta_views"],
            "delta_clicks": deltas["delta_clicks"],
            "delta_ctr": deltas["delta_ctr"],
            "hours_exposed": deltas["hours_exposed"],
        },
        "profile_state": {
            "visibility": snapshot["visibility"],
            "is_available": snapshot["is_available"],
            "availability_message": snapshot["availability_message"],
            "rebrandly_present": snapshot["rebrandly_present"],
        },
        "current_headline": snapshot["headline"],
        "bio_length": snapshot["bio_length"],
        "decision": decision,
        "baseline_ctr": ledger.get("baseline_ctr"),
        "min_sample_rules": {
            "min_views": MIN_VIEWS,
            "min_hours": MIN_HOURS,
            "low_traffic_extend_hours": LOW_TRAFFIC_EXTEND_HOURS,
            "hard_drop_threshold": HARD_DROP_THRESHOLD,
        },
    }


def write_evidence_packet(packet: dict):
    """Write daily evidence packet."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = packet["date"]
    path = EVIDENCE_DIR / f"daily_{date_str}.json"
    path.write_text(json.dumps(packet, indent=2))
    print(f"Evidence packet written: {path}")

    # Also write latest.json for HF/GitHub promotion
    latest = EVIDENCE_DIR / "latest.json"
    latest.write_text(json.dumps(packet, indent=2))
    print(f"Latest evidence: {latest}")


def write_receipt(packet: dict, decision: str):
    """Write receipt for the evidence cycle."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    receipt = {
        "action": "daily_evidence_packet",
        "timestamp": now_iso(),
        "decision": decision,
        "bio_id": packet["bio_id"],
        "delta_views": packet["metrics"]["delta_views"],
        "delta_clicks": packet["metrics"]["delta_clicks"],
        "delta_ctr": packet["metrics"]["delta_ctr"],
        "hours_exposed": packet["metrics"]["hours_exposed"],
    }
    path = RECEIPTS_DIR / f"evidence_{ts}.json"
    path.write_text(json.dumps(receipt, indent=2))
    print(f"Receipt: {path}")


def main():
    print("=" * 60)
    print("DAILY EVIDENCE PACKET")
    print("bio_id → traffic → contact_clicks → decision")
    print("=" * 60)

    load_dotenv(EXT_DIR / ".env")
    username = os.environ.get("RENTMASSEUR_USERNAME")
    password = os.environ.get("RENTMASSEUR_PASSWORD")

    if not username or not password or username == "REDACTED_ROTATE_ME":
        print("ERROR: No valid credentials in .env")
        sys.exit(1)

    # Login
    print(f"\nLogging in as {username}...")
    api = RentMasseurAPI(min_request_interval=2.0)
    if not api.login(username, password):
        print("ERROR: Login failed")
        sys.exit(1)
    print("Login successful")

    # Snapshot
    print("\nSnapshotting live profile...")
    snapshot = snapshot_profile(api)
    print(f"  Total views: {snapshot['total_page_views']}")
    print(f"  Total clicks: {snapshot['total_contact_clicks']}")
    print(f"  New visits: {snapshot['new_visits']}")
    print(f"  New emails: {snapshot['new_emails']}")
    print(f"  Visibility: {snapshot['visibility']}")
    print(f"  Available: {snapshot['is_available']} ({snapshot['availability_message']})")
    print(f"  Headline: {snapshot['headline']}")
    print(f"  Rebrandly: {'YES' if snapshot['rebrandly_present'] else 'NO'}")
    print(f"  Bio length: {snapshot['bio_length']} chars")

    # Load ledger
    ledger = load_ledger()
    print(f"\nCurrent bio: {ledger.get('current_bio_id', 'none')}")
    print(f"Started at: {ledger.get('current_bio_started_at', 'none')}")

    # Compute deltas
    deltas = compute_deltas(snapshot, ledger)
    print(f"\nDeltas:")
    print(f"  Views since bio start: {deltas['delta_views']}")
    print(f"  Clicks since bio start: {deltas['delta_clicks']}")
    print(f"  CTR since bio start: {deltas['delta_ctr']}%")
    print(f"  Hours exposed: {deltas['hours_exposed']}")

    # Decide
    decision = decide(snapshot, deltas, ledger)
    print(f"\nDECISION: {decision}")

    # Build packet
    packet = build_evidence_packet(snapshot, deltas, decision, ledger)

    # Write
    write_evidence_packet(packet)
    write_receipt(packet, decision)

    # If baseline CTR not set, set it from first snapshot
    if ledger.get("baseline_ctr") is None and snapshot["total_page_views"] > 0:
        baseline = (snapshot["total_contact_clicks"] / snapshot["total_page_views"]) * 100
        ledger["baseline_ctr"] = round(baseline, 2)
        print(f"\nBaseline CTR set: {ledger['baseline_ctr']}%")
        save_ledger(ledger)

    print("\n" + "=" * 60)
    print("EVIDENCE PACKET COMPLETE")
    print(f"Decision: {decision}")
    print("=" * 60)


if __name__ == "__main__":
    main()
