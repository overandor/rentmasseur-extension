#!/usr/bin/env python3
"""
Bio Push Pipeline — pushes the winning bio to the live profile and initializes the experiment ledger.

This is the ONLY script that mutates the live profile bio.
It pushes one bio, records the start state, and writes a receipt.

Usage:
  python3 push_bio.py                    # Push the winning bio (variant B)
  python3 push_bio.py A                  # Push variant A (clinical)
  python3 push_bio.py B                  # Push variant B (winning wolf)
  python3 push_bio.py C                  # Push variant C (luxury)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path("/Users/alep/Downloads/rentmasseur-optimizer/rm_pri/py")))
from api_client import RentMasseurAPI

from dotenv import load_dotenv

EXT_DIR = Path(__file__).parent
CONTENT_DIR = EXT_DIR / "content"
BIOS_DIR = CONTENT_DIR / "bios"
RECEIPTS_DIR = EXT_DIR / "receipts"
LEDGER_PATH = CONTENT_DIR / "experiment_ledger.json"

REBRANDLY_LINK = "rebrand.ly/carpathianwolf"

VARIANTS = {
    "A": {
        "id": "bio_A_clinical_recovery",
        "file": "bio_A_clinical_recovery.md",
        "strategy": "clinical_recovery",
        "headline": "KARPATHIAN WOLF — Professional Therapeutic Massage",
    },
    "B": {
        "id": "bio_W_winning_production",
        "file": "bio_W_winning_production.md",
        "strategy": "controlled_wolf",
        "headline": "KARPATHIAN WOLF — Targeted Recovery in Manhattan",
    },
    "C": {
        "id": "bio_C_luxury_concierge",
        "file": "bio_C_luxury_concierge.md",
        "strategy": "luxury_concierge",
        "headline": "KARPATHIAN WOLF — Manhattan's Private Recovery Specialist",
    },
}


def load_bio(filename: str) -> str:
    path = BIOS_DIR / filename
    if not path.exists():
        print(f"ERROR: Bio file not found: {path}")
        sys.exit(1)
    content = path.read_text().strip()
    # Remove markdown header if present
    lines = content.split("\n")
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    bio = "\n".join(lines).strip()
    # Ensure rebrandly link
    if REBRANDLY_LINK not in bio:
        bio += f"\n\nBook: {REBRANDLY_LINK}"
    return bio


def load_ledger() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return {"current_bio_id": None, "current_bio_started_at": None,
            "current_bio_start_views": 0, "current_bio_start_clicks": 0,
            "history": [], "baseline_ctr": None}


def save_ledger(ledger: dict):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))


def main():
    variant_key = sys.argv[1] if len(sys.argv) > 1 else "B"
    if variant_key not in VARIANTS:
        print(f"ERROR: Unknown variant '{variant_key}'. Use A, B, or C.")
        sys.exit(1)

    variant = VARIANTS[variant_key]
    bio_content = load_bio(variant["file"])

    print("=" * 60)
    print(f"BIO PUSH — Variant {variant_key}: {variant['id']}")
    print("=" * 60)
    print(f"  Strategy: {variant['strategy']}")
    print(f"  Headline: {variant['headline']}")
    print(f"  Length: {len(bio_content)} chars")
    print(f"\n  Bio preview:\n{bio_content[:300]}...")

    # Load credentials
    load_dotenv(EXT_DIR / ".env")
    username = os.environ.get("RENTMASSEUR_USERNAME")
    password = os.environ.get("RENTMASSEUR_PASSWORD")

    if not username or not password or username == "REDACTED_ROTATE_ME":
        print("ERROR: No valid credentials in .env")
        sys.exit(1)

    # Login — try saved session first, then fresh login
    print(f"\nLogging in as {username}...")
    api = RentMasseurAPI(min_request_interval=2.0)

    session_path = Path("/Users/alep/Downloads/windsurf-smoke/rm_traffic/session.json")
    if session_path.exists():
        print("Found saved session, loading cookies...")
        session_data = json.loads(session_path.read_text())
        cookies = session_data.get("cookies", [])
        api.load_cookies(cookies)
        # Test with a lightweight request
        try:
            api.get_keeponline()
            print("Saved session is valid")
        except Exception as e:
            print(f"Saved session expired, trying fresh login... ({e})")
            if not api.login(username, password):
                print("ERROR: Login failed (CrowdSec captcha may be active)")
                print("Try again later or use a VPN/different IP")
                sys.exit(1)
    else:
        if not api.login(username, password):
            print("ERROR: Login failed (CrowdSec captcha may be active)")
            sys.exit(1)
    print("Login successful")

    # Capture BEFORE snapshot
    print("\n--- BEFORE snapshot ---")
    stats = api.get_ad_statistics()
    profile_stats = stats.get("profileStatistics", {}) if isinstance(stats, dict) else {}
    before_views = profile_stats.get("totalPageViews", 0)
    before_clicks = profile_stats.get("totalContactClicks", 0)
    print(f"  Total views: {before_views}")
    print(f"  Total clicks: {before_clicks}")

    about = api.get_about()
    assets = about.get("userProps", {}).get("assets", {}) if isinstance(about, dict) else {}
    old_headline = assets.get("headline", "")
    old_bio = assets.get("description", "")
    print(f"  Old headline: {old_headline}")
    print(f"  Old bio length: {len(old_bio)} chars")
    print(f"  Old bio had rebrandly: {REBRANDLY_LINK in old_bio}")

    # Push new bio
    print(f"\n--- PUSHING new bio ---")
    print(f"  Headline: {variant['headline']}")
    try:
        result = api.set_about(headline=variant["headline"], description=bio_content)
        print(f"  API response: {json.dumps(result, indent=2)[:500]}")
        print("  BIO PUSHED SUCCESSFULLY")
    except Exception as e:
        print(f"  ERROR: Failed to push bio: {e}")
        sys.exit(1)

    # Verify
    print(f"\n--- VERIFY ---")
    verify = api.get_about()
    v_assets = verify.get("userProps", {}).get("assets", {}) if isinstance(verify, dict) else {}
    v_headline = v_assets.get("headline", "")
    v_bio = v_assets.get("description", "")
    print(f"  Verified headline: {v_headline}")
    print(f"  Verified bio length: {len(v_bio)} chars")
    print(f"  Rebrandly in live bio: {'YES' if REBRANDLY_LINK in v_bio else 'NO'}")

    # Update experiment ledger
    ledger = load_ledger()
    # Record previous bio in history
    if ledger.get("current_bio_id"):
        ledger["history"].append({
            "bio_id": ledger["current_bio_id"],
            "started_at": ledger.get("current_bio_started_at"),
            "ended_at": now_iso(),
            "start_views": ledger.get("current_bio_start_views", 0),
            "end_views": before_views,
            "start_clicks": ledger.get("current_bio_start_clicks", 0),
            "end_clicks": before_clicks,
        })

    # Set new current bio
    ledger["current_bio_id"] = variant["id"]
    ledger["current_bio_started_at"] = now_iso()
    ledger["current_bio_start_views"] = before_views
    ledger["current_bio_start_clicks"] = before_clicks
    save_ledger(ledger)
    print(f"\n  Experiment ledger updated: {variant['id']}")

    # Write receipt
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    receipt = {
        "action": "bio_push",
        "timestamp": ts.isoformat(),
        "variant": variant_key,
        "bio_id": variant["id"],
        "strategy": variant["strategy"],
        "headline": variant["headline"],
        "bio_length": len(bio_content),
        "rebrandly_present": REBRANDLY_LINK in bio_content,
        "rebrandly_verified_live": REBRANDLY_LINK in v_bio,
        "before_views": before_views,
        "before_clicks": before_clicks,
        "old_headline": old_headline,
        "api_result": "success" if v_headline == variant["headline"] else "mismatch",
    }
    receipt_path = RECEIPTS_DIR / f"bio_push_{ts.strftime('%Y%m%d_%H%M%S')}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))
    print(f"  Receipt: {receipt_path}")

    print("\n" + "=" * 60)
    print("PUSH COMPLETE")
    print(f"  Bio: {variant['id']}")
    print(f"  Headline: {v_headline}")
    print(f"  Rebrandly: {'LIVE' if REBRANDLY_LINK in v_bio else 'NOT FOUND'}")
    print(f"  Baseline views: {before_views}")
    print(f"  Baseline clicks: {before_clicks}")
    print("=" * 60)
    print("\nNext: run daily_evidence.py to track performance")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
