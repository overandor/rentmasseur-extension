#!/usr/bin/env python3
"""
Hourly KPI collector — computes immortality and virality scores from metrics history.

Immortality = profile longevity & staying power
Virality = profile spread velocity & acceleration

Runs hourly via GitHub Actions. Reads metrics from content/metrics_ingest.jsonl,
computes derived KPIs, writes to content/kpis/hourly_kpis.jsonl, and POSTs
to HF Space /api/metrics/ingest if HF_URL is set.
"""

import json
import os
import sys
import time
import math
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

CONTENT_DIR = Path(__file__).parent / "content"
METRICS_PATH = CONTENT_DIR / "metrics_ingest.jsonl"
KPI_DIR = CONTENT_DIR / "kpis"
KPI_PATH = KPI_DIR / "hourly_kpis.jsonl"
RECEIPTS_DIR = Path(__file__).parent / "receipts"

KPI_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

HF_URL = os.getenv("HF_URL", "https://josephrw-rentmasseur-optimizer.hf.space")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def load_metrics() -> List[Dict]:
    """Load all ingested metrics from JSONL."""
    if not METRICS_PATH.exists():
        return []
    metrics = []
    for line in METRICS_PATH.open():
        if line.strip():
            metrics.append(json.loads(line))
    return metrics


def compute_immortality(metrics: List[Dict]) -> Dict:
    """
    Immortality KPI — profile longevity & staying power.
    
    Components:
    - days_online: total days profile has been active
    - views_per_day_trend: is traffic sustaining or declining?
    - visibility_persistence: how consistently is profile visible?
    - availability_stability: how stable is availability?
    - profile_age_score: normalized longevity (0-1)
    - retention_score: views don't drop off over time
    """
    if not metrics:
        return {"score": 0, "grade": "NO_DATA", "components": {}}

    latest = metrics[-1]
    pub = latest.get("public_profile", {})
    dash = latest.get("dashboard", {})

    days_online = pub.get("days_online", 0)
    views_per_day = pub.get("views_per_day", 0)
    profile_visible = dash.get("profile_visible", False)
    available = dash.get("available", False)

    # Profile age score: 1.0 at 1000+ days, scales down
    profile_age_score = min(days_online / 1000.0, 1.0) if days_online > 0 else 0

    # Views per day trend: compare last 3 data points if available
    vpd_values = []
    for m in metrics[-5:]:
        v = m.get("public_profile", {}).get("views_per_day", 0)
        if v > 0:
            vpd_values.append(v)

    if len(vpd_values) >= 2:
        recent_avg = sum(vpd_values[-2:]) / 2
        older_avg = sum(vpd_values[:-2]) / max(len(vpd_values) - 2, 1)
        if older_avg > 0:
            trend_ratio = recent_avg / older_avg
        else:
            trend_ratio = 1.0
        views_per_day_trend = min(max(trend_ratio, 0), 2.0) / 2.0  # normalize 0-1
    else:
        views_per_day_trend = 0.5  # neutral if not enough data

    # Visibility persistence: fraction of snapshots where visible=True
    visibility_count = sum(1 for m in metrics if m.get("dashboard", {}).get("profile_visible", False))
    visibility_persistence = visibility_count / len(metrics) if metrics else 0

    # Availability stability: fraction of snapshots where available=True
    avail_count = sum(1 for m in metrics if m.get("dashboard", {}).get("available", False))
    availability_stability = avail_count / len(metrics) if metrics else 0

    # Retention score: views_per_day doesn't collapse
    if views_per_day > 0:
        retention_score = min(views_per_day / 100.0, 1.0)
    else:
        retention_score = 0

    # Weighted composite
    score = (
        profile_age_score * 0.25 +
        views_per_day_trend * 0.25 +
        visibility_persistence * 0.20 +
        availability_stability * 0.15 +
        retention_score * 0.15
    )

    # Grade
    if score >= 0.80:
        grade = "IMMORTAL"
    elif score >= 0.60:
        grade = "RESILIENT"
    elif score >= 0.40:
        grade = "STABLE"
    elif score >= 0.20:
        grade = "FRAGILE"
    else:
        grade = "DECLINING"

    return {
        "score": round(score, 4),
        "grade": grade,
        "components": {
            "days_online": days_online,
            "views_per_day": views_per_day,
            "profile_age_score": round(profile_age_score, 4),
            "views_per_day_trend": round(views_per_day_trend, 4),
            "visibility_persistence": round(visibility_persistence, 4),
            "availability_stability": round(availability_stability, 4),
            "retention_score": round(retention_score, 4),
        }
    }


def compute_virality(metrics: List[Dict]) -> Dict:
    """
    Virality KPI — profile spread velocity & acceleration.
    
    Components:
    - views_velocity: rate of new views per hour
    - views_acceleration: is velocity increasing?
    - contact_click_velocity: rate of new contact clicks
    - new_visitor_rate: new visits as fraction of total views
    - bookmark_rate: bookmarks per view
    - email_rate: emails per view
    - spread_score: composite velocity metric
    """
    if not metrics:
        return {"score": 0, "grade": "NO_DATA", "components": {}}

    latest = metrics[-1]
    dash = latest.get("dashboard", {})

    profile_views = dash.get("profile_views", 0)
    contact_clicks = dash.get("contact_clicks", 0)
    new_visits = dash.get("new_visits", 0)
    new_emails = dash.get("new_emails", 0)
    online_bookmarks = dash.get("online_bookmarks", 0)

    # Views velocity: views gained since last snapshot
    views_velocity = 0
    views_acceleration = 0
    if len(metrics) >= 2:
        prev_views = metrics[-2].get("dashboard", {}).get("profile_views", 0)
        views_velocity = max(profile_views - prev_views, 0)

    if len(metrics) >= 3:
        prev_prev_views = metrics[-3].get("dashboard", {}).get("profile_views", 0)
        prev_views = metrics[-2].get("dashboard", {}).get("profile_views", 0)
        v1 = max(prev_views - prev_prev_views, 0)
        v2 = max(profile_views - prev_views, 0)
        if v1 > 0:
            views_acceleration = (v2 - v1) / v1
        elif v2 > 0:
            views_acceleration = 1.0

    # Contact click velocity
    contact_click_velocity = 0
    if len(metrics) >= 2:
        prev_clicks = metrics[-2].get("dashboard", {}).get("contact_clicks", 0)
        contact_click_velocity = max(contact_clicks - prev_clicks, 0)

    # Rates
    new_visitor_rate = new_visits / profile_views if profile_views > 0 else 0
    bookmark_rate = online_bookmarks / profile_views if profile_views > 0 else 0
    email_rate = new_emails / profile_views if profile_views > 0 else 0
    contact_click_rate = contact_clicks / profile_views if profile_views > 0 else 0

    # Spread score: how fast is the profile reaching new people
    # Normalize components to 0-1
    views_velocity_norm = min(views_velocity / 50.0, 1.0)  # 50+ new views per snapshot = max
    views_accel_norm = min(max(views_acceleration, 0) / 0.5, 1.0)  # 50% acceleration = max
    contact_velocity_norm = min(contact_click_velocity / 10.0, 1.0)  # 10+ new clicks = max
    new_visitor_norm = min(new_visitor_rate / 0.05, 1.0)  # 5% new visitor rate = max
    bookmark_norm = min(bookmark_rate / 0.01, 1.0)  # 1% bookmark rate = max
    email_norm = min(email_rate / 0.01, 1.0)  # 1% email rate = max
    ctr_norm = min(contact_click_rate / 0.10, 1.0)  # 10% CTR = max

    score = (
        views_velocity_norm * 0.25 +
        views_accel_norm * 0.15 +
        contact_velocity_norm * 0.20 +
        new_visitor_norm * 0.15 +
        bookmark_norm * 0.05 +
        email_norm * 0.05 +
        ctr_norm * 0.15
    )

    # Grade
    if score >= 0.70:
        grade = "VIRAL"
    elif score >= 0.50:
        grade = "ACCELERATING"
    elif score >= 0.30:
        grade = "STEADY"
    elif score >= 0.15:
        grade = "SLOW"
    else:
        grade = "STAGNANT"

    return {
        "score": round(score, 4),
        "grade": grade,
        "components": {
            "profile_views": profile_views,
            "views_velocity": views_velocity,
            "views_acceleration": round(views_acceleration, 4),
            "contact_clicks": contact_clicks,
            "contact_click_velocity": contact_click_velocity,
            "new_visits": new_visits,
            "new_visitor_rate": round(new_visitor_rate, 4),
            "online_bookmarks": online_bookmarks,
            "bookmark_rate": round(bookmark_rate, 4),
            "new_emails": new_emails,
            "email_rate": round(email_rate, 4),
            "contact_click_rate": round(contact_click_rate, 4),
        }
    }


def write_receipt(kpi_packet: Dict) -> Path:
    """Write a tamper-evident receipt for the KPI computation."""
    ts = datetime.now(timezone.utc).isoformat()
    receipt = {
        "id": f"kpi_{int(time.time())}",
        "timestamp": ts,
        "action": "hourly_kpi_computation",
        "data": kpi_packet,
    }
    path = RECEIPTS_DIR / f"kpi_{ts.replace(':', '-').replace('+', '-')}.json"
    with path.open("w") as f:
        json.dump(receipt, f, indent=2)
    return path


def post_to_hf(kpi_packet: Dict) -> bool:
    """POST KPI packet to HF Space /api/metrics/ingest."""
    if not HF_URL:
        return False
    try:
        headers = {"Content-Type": "application/json"}
        if ADMIN_TOKEN:
            headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
        r = requests.post(
            f"{HF_URL}/api/metrics/ingest",
            json=kpi_packet,
            headers=headers,
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"HF POST failed: {e}", file=sys.stderr)
        return False


def main():
    print("=== Hourly KPI Collection ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    metrics = load_metrics()
    print(f"Loaded {len(metrics)} metric snapshots")

    immortality = compute_immortality(metrics)
    virality = compute_virality(metrics)

    kpi_packet = {
        "packet_type": "rm_hourly_kpis",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "immortality": immortality,
        "virality": virality,
        "metrics_snapshots_used": len(metrics),
    }

    # Write to JSONL
    with KPI_PATH.open("a") as f:
        f.write(json.dumps(kpi_packet) + "\n")
    print(f"KPIs written to {KPI_PATH}")

    # Write receipt
    receipt_path = write_receipt(kpi_packet)
    print(f"Receipt: {receipt_path}")

    # Print summary
    print()
    print(f"IMMORTALITY: {immortality['score']:.4f} ({immortality['grade']})")
    for k, v in immortality["components"].items():
        print(f"  {k}: {v}")

    print()
    print(f"VIRALITY: {virality['score']:.4f} ({virality['grade']})")
    for k, v in virality["components"].items():
        print(f"  {k}: {v}")

    # POST to HF
    if HF_URL:
        ok = post_to_hf(kpi_packet)
        if ok:
            print(f"\nPOSTed to {HF_URL}/api/metrics/ingest -> 200")
        else:
            print(f"\nHF POST failed (non-fatal)")

    print("\n=== KPI Collection Complete ===")


if __name__ == "__main__":
    main()
