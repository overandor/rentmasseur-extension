#!/usr/bin/env python3
"""
Bio Rotation Pipeline — seeds rotator, picks best bio, pushes to live profile.

Steps:
1. Load 4 bio variants from content/bios/
2. Seed rotator_engine state JSON
3. Run rotator --rotate bio to pick next
4. Login to RentMasseur API
5. Push bio via set_about(headline, description)
6. Write receipt
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add rm_pri to path (api_client lives in the optimizer repo)
sys.path.insert(0, str(Path("/Users/alep/Downloads/rentmasseur-optimizer/rm_pri/py")))

from api_client import RentMasseurAPI

CONTENT_DIR = Path(__file__).parent / "content"
BIOS_DIR = CONTENT_DIR / "bios"
RECEIPTS_DIR = Path(__file__).parent / "receipts"
RL_STATE_PATH = CONTENT_DIR / "rl_state.json"

# The 4 approved bio variants with rebrandly link
BIO_VARIANTS = [
    {
        "id": "bio_D_funny_direct_cta",
        "file": "bio_D_funny_direct_cta.md",
        "strategy": "funny_direct_cta",
        "headline": "KARPATHIAN WOLF — Deep Tissue & Sports Recovery",
    },
    {
        "id": "bio_B_karpathian_wolf",
        "file": "bio_B_karpathian_wolf.md",
        "strategy": "brand_identity",
        "headline": "KARPATHIAN WOLF — Targeted Recovery for Men",
    },
    {
        "id": "bio_A_clinical_recovery",
        "file": "bio_A_clinical_recovery.md",
        "strategy": "clinical_recovery",
        "headline": "KARPATHIAN WOLF — Professional Therapeutic Massage",
    },
    {
        "id": "bio_20260626_targeted_recovery_v2",
        "file": "bio_20260626_targeted_recovery_v2.md",
        "strategy": "targeted_recovery_v2",
        "headline": "KARPATHIAN WOLF — Targeted Recovery, Not Generic Relaxation",
    },
]

REBRANDLY_LINK = "rebrand.ly/carpathianwolf"


def load_bio_content(filename: str) -> str:
    """Load bio markdown and clean it for the API."""
    path = BIOS_DIR / filename
    if not path.exists():
        print(f"ERROR: Bio file not found: {path}")
        sys.exit(1)
    content = path.read_text().strip()
    # Remove markdown header line (# Bio X — ...)
    lines = content.split("\n")
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    bio = "\n".join(lines).strip()
    # Ensure rebrandly link is present
    if REBRANDLY_LINK not in bio:
        bio += f"\n\nBook: {REBRANDLY_LINK}"
    return bio


def seed_rotator():
    """Seed the rotator engine's RL state with the 4 bio variants."""
    state = {
        "stores": {
            "bio": {},
        },
        "current": {},
        "rotations": {},
    }

    for variant in BIO_VARIANTS:
        bio_content = load_bio_content(variant["file"])
        state["stores"]["bio"][variant["id"]] = {
            "content": bio_content[:500],
            "strategy": variant["strategy"],
            "total_reward": 0,
            "delta_reward": 0,
            "times_used": 0,
            "age_hours": 0,
        }

    RL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RL_STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"Seeded rotator state with {len(BIO_VARIANTS)} bio variants at {RL_STATE_PATH}")


def run_rotator_pick() -> dict:
    """Run the C++ rotator engine to pick the next bio."""
    rotator = Path(__file__).parent / "rotator_engine"
    if not rotator.exists():
        print("Compiling rotator_engine...")
        subprocess.run(
            ["g++", "-O3", "-std=c++17", "-pthread", "rotator_engine.cpp", "-o", "rotator_engine"],
            cwd=Path(__file__).parent, check=True
        )

    result = subprocess.run(
        ["./rotator_engine", "--rotate", "bio", "--dir", str(CONTENT_DIR)],
        cwd=Path(__file__).parent, capture_output=True, text=True
    )

    print(f"Rotator exit code: {result.returncode}")
    print(f"Rotator stdout: {result.stdout.strip()}")
    if result.stderr:
        print(f"Rotator stderr: {result.stderr.strip()}")

    if result.returncode != 0:
        print("Rotator failed to pick a bio")
        sys.exit(1)

    # Parse output: "Next bio: bio_D_funny_direct_cta (strategy: funny_direct_cta, uses: 0, reward: 0)"
    output = result.stdout.strip()
    for variant in BIO_VARIANTS:
        if variant["id"] in output:
            print(f"Selected bio: {variant['id']} (strategy: {variant['strategy']})")
            return variant

    print(f"Could not parse selected bio from: {output}")
    sys.exit(1)


def push_bio_to_profile(variant: dict):
    """Login to RentMasseur and push the selected bio."""
    bio_content = load_bio_content(variant["file"])

    # Verify rebrandly link
    if REBRANDLY_LINK not in bio_content:
        print(f"ERROR: Bio does not contain rebrandly link: {REBRANDLY_LINK}")
        sys.exit(1)

    print(f"\nBio to push ({variant['id']}):")
    print(f"  Headline: {variant['headline']}")
    print(f"  Length: {len(bio_content)} chars")
    print(f"  Rebrandly link: PRESENT")
    print(f"  Content preview: {bio_content[:200]}...")

    # Load credentials from .env
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    username = os.environ.get("RENTMASSEUR_USERNAME")
    password = os.environ.get("RENTMASSEUR_PASSWORD")

    if not username or not password or username == "REDACTED_ROTATE_ME":
        print("ERROR: No valid credentials in .env")
        sys.exit(1)

    print(f"\nLogging in as {username}...")
    api = RentMasseurAPI(min_request_interval=2.0)

    if not api.login(username, password):
        print("ERROR: Login failed")
        sys.exit(1)

    print("Login successful")

    # Check current bio first
    print("\nFetching current bio...")
    try:
        current = api.get_about()
        print(f"Current headline: {current.get('headline', 'unknown')}")
        current_desc = current.get("description", "")
        if REBRANDLY_LINK in current_desc:
            print("Current bio already has rebrandly link")
    except Exception as e:
        print(f"Warning: Could not fetch current bio: {e}")

    # Push new bio
    print(f"\nPushing bio: {variant['id']}")
    print(f"  Headline: {variant['headline']}")
    print(f"  Description: {bio_content[:100]}...")

    try:
        result = api.set_about(headline=variant["headline"], description=bio_content)
        print(f"API response: {json.dumps(result, indent=2)}")
        print("BIO UPDATED SUCCESSFULLY")
    except Exception as e:
        print(f"ERROR: Failed to update bio: {e}")
        sys.exit(1)

    # Write receipt
    write_receipt(variant, bio_content, result)

    # Verify
    print("\nVerifying update...")
    try:
        verify = api.get_about()
        print(f"Verified headline: {verify.get('headline', 'unknown')}")
        verified_desc = verify.get("description", "")
        if REBRANDLY_LINK in verified_desc:
            print("VERIFIED: Rebrandly link is live in profile bio")
        else:
            print("WARNING: Rebrandly link not found in verified bio")
        print(f"Verified bio length: {len(verified_desc)} chars")
    except Exception as e:
        print(f"Warning: Could not verify: {e}")


def write_receipt(variant: dict, bio_content: str, api_result: dict):
    """Write a receipt for the bio update."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    receipt = {
        "action": "bio_rotation_push",
        "timestamp": ts.isoformat(),
        "variant_id": variant["id"],
        "strategy": variant["strategy"],
        "headline": variant["headline"],
        "bio_length": len(bio_content),
        "rebrandly_link": REBRANDLY_LINK,
        "rebrandly_present": REBRANDLY_LINK in bio_content,
        "api_result": api_result,
        "status": "pushed",
    }
    receipt_path = RECEIPTS_DIR / f"bio_push_{ts.strftime('%Y%m%d_%H%M%S')}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))
    print(f"\nReceipt written: {receipt_path}")


def main():
    print("=" * 60)
    print("RM-PRI BIO ROTATION PIPELINE")
    print("=" * 60)

    # Step 1: Seed rotator
    print("\n--- Step 1: Seed rotator ---")
    seed_rotator()

    # Step 2: Pick best bio via C++ rotator
    print("\n--- Step 2: Rotator picks next bio ---")
    selected = run_rotator_pick()

    # Step 3: Push to live profile
    print("\n--- Step 3: Push bio to live profile ---")
    push_bio_to_profile(selected)

    # Step 4: Show rotator report
    print("\n--- Step 4: Rotator report ---")
    rotator = Path(__file__).parent / "rotator_engine"
    report = subprocess.run(
        ["./rotator_engine", "--report", "--dir", str(CONTENT_DIR)],
        cwd=Path(__file__).parent, capture_output=True, text=True
    )
    print(report.stdout)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
