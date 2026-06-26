#!/usr/bin/env python3
"""
Metrics collector — accepts first-party data from the Chrome extension or manual uploads.
No automated login. No Selenium. No captcha-bypassing.

Data sources:
  1. Chrome extension sends metrics to HF Space /api/ingest (user-approved, first-party)
  2. Manual JSON upload via CI/CD workflow_dispatch inputs
  3. Dashboard screenshot OCR (user-provided, not automated)

This script processes ingested metrics and updates the availability/RL state files.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTENT_DIR = Path("content")
AVAILABILITY_FILE = Path("availability.json")
METRICS_INGEST = CONTENT_DIR / "metrics_ingest.jsonl"


def process_ingested_metrics():
    """Read all ingested metrics and produce a summary."""
    if not METRICS_INGEST.exists():
        print("[metrics] No ingested metrics file found.")
        return {"status": "no_data", "message": "No metrics ingested yet."}

    metrics = []
    with open(METRICS_INGEST, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                metrics.append(entry)
            except json.JSONDecodeError:
                continue

    if not metrics:
        return {"status": "no_data", "message": "Metrics file is empty."}

    latest = metrics[-1]
    summary = {
        "status": "ok",
        "total_ingested": len(metrics),
        "latest_timestamp": latest.get("timestamp", ""),
        "latest_metrics": latest,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Update availability file if metrics contain availability info
    body = latest.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {}

    if "is_available" in body or "availability" in body:
        avail = {
            "status": "available" if body.get("is_available") else "unknown",
            "checked_at": latest.get("timestamp", ""),
            "source": "extension_first_party",
            "mode": "user_approved",
        }
        with open(AVAILABILITY_FILE, "w") as f:
            json.dump(avail, f, indent=2)
        print(f"[metrics] Updated availability: {avail['status']}")

    # Save metrics summary
    CONTENT_DIR.mkdir(exist_ok=True)
    with open(CONTENT_DIR / "metrics_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[metrics] Processed {len(metrics)} ingested metric entries.")
    return summary


def generate_proof():
    """Generate a proof/receipt file for this run."""
    receipts_dir = Path("receipts")
    receipts_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    proof = {
        "action": "metrics-collector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "first_party_extension_or_manual",
        "automated_login": False,
        "captcha_bypassed": False,
        "metrics_processed": 0,
        "availability_updated": AVAILABILITY_FILE.exists(),
        "status": "completed",
    }

    summary = process_ingested_metrics()
    proof["metrics_processed"] = summary.get("total_ingested", 0)
    proof["summary"] = summary

    proof_path = receipts_dir / f"metrics_{timestamp}.json"
    with open(proof_path, "w") as f:
        json.dump(proof, f, indent=2)

    print(f"[proof] Receipt written: {proof_path}")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RentMasseur first-party metrics collector")
    parser.add_argument("--process", action="store_true", help="Process ingested metrics")
    parser.add_argument("--proof", action="store_true", help="Generate proof file only")
    args = parser.parse_args()

    if args.proof or args.process or not sys.argv[1:]:
        result = generate_proof()
        print(json.dumps(result, indent=2))
