#!/usr/bin/env python3
"""One-time manual bio deployment for controlled experiment 001.

Usage:
    python3 deploy_bio_experiment.py --bio controlled_wolf_v1 --dry-run
    python3 deploy_bio_experiment.py --bio controlled_wolf_v1

This is NOT a scheduled automation. It is a one-time manual deployment
of an approved candidate bio for a controlled experiment.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
BIOS_DIR = os.path.join(CONTENT_DIR, "bios")
EXPERIMENTS_DIR = os.path.join(CONTENT_DIR, "experiments")
RECEIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")


def load_bio(bio_id: str) -> str:
    path = os.path.join(BIOS_DIR, f"{bio_id}.md")
    if not os.path.exists(path):
        logger.error(f"Bio file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_experiment(exp_id: str) -> dict:
    path = os.path.join(EXPERIMENTS_DIR, f"{exp_id}.json")
    if not os.path.exists(path):
        logger.error(f"Experiment file not found: {path}")
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def write_receipt(bio_id: str, experiment_id: str, success: bool, notes: str = ""):
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    receipt = {
        "action": "bio_deploy",
        "bio_id": bio_id,
        "experiment_id": experiment_id,
        "success": success,
        "timestamp": ts,
        "notes": notes,
    }
    path = os.path.join(RECEIPTS_DIR, f"deploy_{bio_id}_{ts.replace(':', '-')}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=2)
    logger.info(f"Receipt written: {path}")
    return path


def deploy_bio(bio_text: str, headless: bool = False) -> bool:
    """Log in and update the profile bio on RentMasseur via Selenium."""
    from rentmasseur_core import setup_driver, login, update_bio, save_bio_field

    driver = setup_driver(headless=headless)
    try:
        if not login(driver):
            logger.error("Login failed - cannot deploy bio")
            return False

        logger.info("Login successful, locating bio field...")
        result = update_bio(driver, "")
        if result is None or (isinstance(result, dict) and result.get("error")):
            logger.error("Could not find bio field on profile settings")
            return False

        field_info, current_bio = result
        logger.info(f"Current bio preview: {current_bio[:80]}...")

        saved = save_bio_field(driver, field_info, bio_text)
        if saved:
            logger.info("Bio deployed successfully!")
            return True
        else:
            logger.error("Failed to save bio")
            return False
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="One-time manual bio deployment for controlled experiment")
    parser.add_argument("--bio", required=True, help="Bio ID (e.g. controlled_wolf_v1)")
    parser.add_argument("--experiment", default="exp_001_targeted_wolf", help="Experiment ID")
    parser.add_argument("--dry-run", action="store_true", help="Show bio without updating profile")
    parser.add_argument("--headless", default="false", help="Run headless (true/false)")
    args = parser.parse_args()

    bio_text = load_bio(args.bio)
    exp = load_experiment(args.experiment)

    print(f"\n{'='*60}")
    print(f"EXPERIMENT: {exp['experiment_id']}")
    print(f"BIO ID: {args.bio}")
    print(f"VARIABLE: {exp['variable']}")
    print(f"FROZEN: photos={exp['photos_frozen']} price={exp['price_frozen']} services={exp['services_frozen']} availability={exp['availability_frozen']}")
    print(f"BIO LENGTH: {len(bio_text)} chars")
    print(f"{'='*60}")
    print(bio_text)
    print(f"{'='*60}\n")

    if args.dry_run:
        logger.info("Dry run - not updating profile")
        write_receipt(args.bio, args.experiment, False, "dry_run_only")
        return

    headless = args.headless.lower() == "true"
    success = deploy_bio(bio_text, headless=headless)
    write_receipt(args.bio, args.experiment, success, "manual_deploy" if success else "deploy_failed")

    if success:
        print("\nBio deployed. Now:")
        print("1. Freeze all other profile variables (photos, prices, services)")
        print("2. Wait 24-48 hours or 100+ new profile views")
        print("3. Capture after-snapshot metrics")
        print("4. POST to /api/metrics/ingest with after data")
        print("5. Check /api/decision/latest for verdict")
    else:
        print("\nDeploy failed. Check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
