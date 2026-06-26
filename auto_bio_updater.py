#!/usr/bin/env python3
"""Auto bio updater — picks the best bio from daily generated content
and updates the RentMasseur profile via Selenium automation.

Reads the mass analysis report to find the recommended bio, or picks
the longest fresh bio if no analysis exists.

Usage:
    python3 auto_bio_updater.py
    python3 auto_bio_updater.py --strategy sensory_luxury
    python3 auto_bio_updater.py --dry-run
"""

import argparse
import json
import os
import sys
import glob
import logging
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
BIOS_DIR = os.path.join(CONTENT_DIR, "bios")


def find_best_bio(preferred_strategy: Optional[str] = None) -> Optional[str]:
    """Find the best bio from today's generated content."""
    today = datetime.now().strftime("%Y%m%d")

    if preferred_strategy:
        filepath = os.path.join(BIOS_DIR, f"{today}_{preferred_strategy}.md")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        logger.warning("No bio found for strategy %s today, falling back to best", preferred_strategy)

    # Check mass analysis for recommendation
    analysis_path = os.path.join(CONTENT_DIR, f"mass_analysis_{today}.md")
    if os.path.exists(analysis_path):
        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = f.read()
        logger.info("Found mass analysis report (%d chars)", len(analysis))

    # Find all of today's bios and pick the longest
    bio_files = glob.glob(os.path.join(BIOS_DIR, f"{today}_*.md"))
    if not bio_files:
        # Fall back to most recent day
        all_bios = sorted(glob.glob(os.path.join(BIOS_DIR, "*.md")), reverse=True)
        if all_bios:
            bio_files = [all_bios[0]]
            logger.info("No bios for today, using most recent: %s", all_bios[0])

    if not bio_files:
        logger.error("No bios found in %s", BIOS_DIR)
        return None

    best_bio = None
    best_len = 0
    for filepath in bio_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if len(content) > best_len:
            best_len = len(content)
            best_bio = content
            logger.info("Candidate: %s (%d chars)", os.path.basename(filepath), len(content))

    if best_bio:
        logger.info("Selected best bio: %d chars", len(best_bio))
    return best_bio


def update_profile_bio(bio_text: str, headless: bool = True) -> bool:
    """Log in and update the profile bio on RentMasseur."""
    from rentmasseur_core import setup_driver, login, update_bio, save_bio_field

    driver = setup_driver(headless=headless)
    try:
        if not login(driver):
            logger.error("Login failed — cannot update bio")
            return False

        logger.info("Login successful, searching for bio field...")
        result = update_bio(driver, "")
        if result is None or (isinstance(result, dict) and result.get("error")):
            logger.error("Could not find bio field on profile settings")
            return False

        field_info, current_bio = result
        logger.info("Current bio: %s...", current_bio[:80])

        saved = save_bio_field(driver, field_info, bio_text)
        if saved:
            logger.info("Bio updated successfully!")
            return True
        else:
            logger.error("Failed to save bio")
            return False
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Auto-update RentMasseur profile bio from daily content")
    parser.add_argument("--strategy", help="Use a specific strategy's bio instead of auto-selecting")
    parser.add_argument("--dry-run", action="store_true", help="Show selected bio without updating profile")
    parser.add_argument("--headless", default="true", help="Run headless (true/false)")
    args = parser.parse_args()

    bio = find_best_bio(preferred_strategy=args.strategy)
    if not bio:
        logger.error("No bio available to update")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"SELECTED BIO ({len(bio)} chars):")
    print(f"{'='*60}")
    print(bio[:200] + "..." if len(bio) > 200 else bio)
    print(f"{'='*60}\n")

    if args.dry_run:
        logger.info("Dry run — not updating profile")
        sys.exit(0)

    headless = args.headless.lower() != "false"
    success = update_profile_bio(bio, headless=headless)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
