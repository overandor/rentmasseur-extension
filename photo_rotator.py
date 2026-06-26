#!/usr/bin/env python3
"""Photo rotator — rotates profile photos on RentMasseur dynamically.

Manages a pool of photos, rotates them on a schedule, and tracks which photos
perform best (correlated with RL feedback). Supports uploading, reordering,
and setting primary photo.

Usage:
    python3 photo_rotator.py                    # rotate to next photo
    python3 photo_rotator.py --add /path/to/photo.jpg   # add photo to pool
    python3 photo_rotator.py --list             # list photo pool
    python3 photo_rotator.py --report           # show performance per photo
"""

import argparse
import json
import os
import sys
import time
import shutil
import logging
from datetime import datetime, timezone
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

RENTMASSEUR_USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
RENTMASSEUR_PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
PHOTO_POOL_DIR = os.path.join(CONTENT_DIR, "photos")
PHOTO_STATE_PATH = os.path.join(CONTENT_DIR, "photo_state.json")
PROFILE_PHOTOS_URL = "https://rentmasseur.com/settings/photos"


def _load_photo_state() -> dict:
    if os.path.exists(PHOTO_STATE_PATH):
        try:
            with open(PHOTO_STATE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "photos": [],
        "current_photo_index": 0,
        "rotation_count": 0,
        "photo_rewards": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_photo_state(state: dict):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    with open(PHOTO_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def add_photo_to_pool(filepath: str, label: str = "") -> str:
    """Add a photo to the rotation pool."""
    os.makedirs(PHOTO_POOL_DIR, exist_ok=True)
    if not os.path.exists(filepath):
        logger.error("Photo not found: %s", filepath)
        return ""

    ext = os.path.splitext(filepath)[1] or ".jpg"
    photo_id = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(_load_photo_state().get('photos', []))}"
    dest = os.path.join(PHOTO_POOL_DIR, f"{photo_id}{ext}")
    shutil.copy2(filepath, dest)

    state = _load_photo_state()
    state["photos"].append({
        "id": photo_id,
        "path": dest,
        "label": label or photo_id,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "times_used": 0,
    })
    _save_photo_state(state)
    logger.info("Added photo to pool: %s (%s)", photo_id, dest)
    return photo_id


def get_next_photo() -> Optional[dict]:
    """Get the next photo in rotation."""
    state = _load_photo_state()
    photos = state.get("photos", [])
    if not photos:
        logger.warning("No photos in pool — add some with --add /path/to/photo.jpg")
        return None

    # Pick least-recently-used photo, weighted by reward
    sorted_photos = sorted(photos, key=lambda p: (p.get("times_used", 0), state.get("photo_rewards", {}).get(p["id"], 0)))
    next_photo = sorted_photos[0]

    state["current_photo_index"] = photos.index(next_photo)
    state["rotation_count"] = state.get("rotation_count", 0) + 1
    next_photo["times_used"] = next_photo.get("times_used", 0) + 1
    next_photo["last_used"] = datetime.now(timezone.utc).isoformat()
    _save_photo_state(state)

    logger.info("Next photo: %s (used %d times)", next_photo["id"], next_photo["times_used"])
    return next_photo


def rotate_photo_on_profile(photo_path: str) -> bool:
    """Upload and set a photo as primary on RentMasseur profile."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from rentmasseur_core import login, dismiss_popups, POPUP_DISMISS_SELECTORS

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        try:
            if not login(driver):
                logger.error("Login failed")
                return False

            logger.info("Navigating to photos settings: %s", PROFILE_PHOTOS_URL)
            driver.get(PROFILE_PHOTOS_URL)
            time.sleep(5)
            dismiss_popups(driver)
            time.sleep(2)

            # Find file upload input
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if not file_inputs:
                logger.error("No file upload input found on photos page")
                return False

            file_inputs[0].send_keys(os.path.abspath(photo_path))
            logger.info("Photo uploaded, waiting for processing...")
            time.sleep(10)

            # Try to set as primary/make main
            make_primary_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Make Main') or contains(text(), 'Set Primary') or contains(text(), 'Make Primary')]")
            if make_primary_btns:
                driver.execute_script("arguments[0].click();", make_primary_btns[0])
                time.sleep(3)
                logger.info("Set as primary photo")

            # Save
            save_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Save') or @type='submit']")
            if save_btns:
                driver.execute_script("arguments[0].click();", save_btns[-1])
                time.sleep(3)

            logger.info("Photo rotation complete")
            return True
        finally:
            driver.quit()
    except Exception as e:
        logger.error("Photo rotation error: %s", e)
        return False


def list_photos():
    state = _load_photo_state()
    photos = state.get("photos", [])
    print(f"\nPhoto Pool: {len(photos)} photos")
    print(f"Rotations: {state.get('rotation_count', 0)}")
    for p in photos:
        reward = state.get("photo_rewards", {}).get(p["id"], 0)
        print(f"  {p['id']}: used {p.get('times_used', 0)}x, reward={reward}, label={p.get('label', '')}")


def photo_report() -> str:
    state = _load_photo_state()
    lines = ["=" * 60, "PHOTO ROTATION REPORT", "=" * 60]
    lines.append(f"Total photos: {len(state.get('photos', []))}")
    lines.append(f"Total rotations: {state.get('rotation_count', 0)}")
    for p in state.get("photos", []):
        reward = state.get("photo_rewards", {}).get(p["id"], 0)
        lines.append(f"  {p['id']}: used={p.get('times_used', 0)}, reward={reward}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Photo rotator for RentMasseur")
    parser.add_argument("--add", help="Add photo to pool")
    parser.add_argument("--label", default="", help="Label for added photo")
    parser.add_argument("--list", action="store_true", help="List photo pool")
    parser.add_argument("--report", action="store_true", help="Show photo report")
    parser.add_argument("--dry-run", action="store_true", help="Don't upload, just pick next")
    args = parser.parse_args()

    if args.add:
        add_photo_to_pool(args.add, args.label)
        return

    if args.list:
        list_photos()
        return

    if args.report:
        print(photo_report())
        return

    # Default: rotate
    photo = get_next_photo()
    if not photo:
        sys.exit(1)

    print(f"Next photo: {photo['id']} ({photo['path']})")
    if args.dry_run:
        logger.info("Dry run — not uploading")
        return

    success = rotate_photo_on_profile(photo["path"])
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
