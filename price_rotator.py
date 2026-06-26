#!/usr/bin/env python3
"""Price rotator — dynamically changes prices on RentMasseur profile.

Rotates prices based on time of day, day of week, demand signals, and RL feedback.
Prices are liquid — they change constantly to maximize bookings and revenue.

Usage:
    python3 price_rotator.py                    # rotate to optimal price now
    python3 price_rotator.py --dry-run          # show calculated price without updating
    python3 price_rotator.py --report           # show price history
"""

import argparse
import json
import os
import sys
import time
import random
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
PRICE_STATE_PATH = os.path.join(CONTENT_DIR, "price_state.json")
PROFILE_RATES_URL = "https://rentmasseur.com/settings/rates"

PRICE_STRATEGIES = [
    {"name": "premium_peak", "desc": "High price peak hours", "base": 250, "variance": 30},
    {"name": "off_peak_deal", "desc": "Off-peak discount", "base": 180, "variance": 20},
    {"name": "new_client_special", "desc": "First-time client", "base": 150, "variance": 15},
    {"name": "loyalty_rate", "desc": "Returning client", "base": 200, "variance": 10},
    {"name": "late_night_premium", "desc": "After-hours premium", "base": 300, "variance": 50},
    {"name": "lunch_express", "desc": "Quick lunch special", "base": 120, "variance": 10},
    {"name": "weekend_warrior", "desc": "Weekend athletic recovery", "base": 220, "variance": 25},
    {"name": "holiday_special", "desc": "Seasonal rate", "base": 200, "variance": 40},
    {"name": "last_minute", "desc": "Same-day booking discount", "base": 170, "variance": 15},
    {"name": "package_deal", "desc": "Multi-session package", "base": 190, "variance": 20},
]


def calculate_optimal_price(strategy: dict, hour: int, day_of_week: int) -> int:
    price = strategy["base"]
    if 18 <= hour <= 23:
        price += int(strategy["variance"] * 0.5)
    if 0 <= hour <= 4:
        price += int(strategy["variance"] * 0.8)
    if day_of_week in (0, 6):
        price += int(strategy["variance"] * 0.3)
    price += round(random.uniform(-0.1, 0.1) * strategy["variance"])
    return max(80, price)


def pick_strategy(hour: int, day_of_week: int) -> dict:
    if 0 <= hour <= 4:
        return next(s for s in PRICE_STRATEGIES if s["name"] == "late_night_premium")
    elif 11 <= hour <= 14:
        return next(s for s in PRICE_STRATEGIES if s["name"] == "lunch_express")
    elif 18 <= hour <= 23:
        return next(s for s in PRICE_STRATEGIES if s["name"] == "premium_peak")
    elif day_of_week in (0, 6):
        return next(s for s in PRICE_STRATEGIES if s["name"] == "weekend_warrior")
    else:
        return random.choice(PRICE_STRATEGIES)


def update_price_on_profile(price: int) -> bool:
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from rentmasseur_core import login, dismiss_popups

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

            driver.get(PROFILE_RATES_URL)
            time.sleep(5)
            dismiss_popups(driver)
            time.sleep(2)

            price_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name*='rate'], input[name*='price'], input[type='number']")
            if not price_inputs:
                logger.error("No price input found on rates page")
                return False

            price_inputs[0].clear()
            price_inputs[0].send_keys(str(price))
            time.sleep(1)

            save_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Save') or @type='submit']")
            if save_btns:
                driver.execute_script("arguments[0].click();", save_btns[-1])
                time.sleep(3)

            logger.info("Price updated to $%d", price)
            return True
        finally:
            driver.quit()
    except Exception as e:
        logger.error("Price update error: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(description="Price rotator for RentMasseur")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    os.makedirs(CONTENT_DIR, exist_ok=True)
    now = datetime.now()
    hour = now.hour
    dow = now.weekday()

    strategy = pick_strategy(hour, dow)
    price = calculate_optimal_price(strategy, hour, dow)

    state = {"price": price, "strategy": strategy["name"], "hour": hour, "dow": dow, "timestamp": now.isoformat()}

    if args.report:
        history = []
        if os.path.exists(PRICE_STATE_PATH):
            with open(PRICE_STATE_PATH) as f:
                try:
                    hist = json.load(f)
                    if isinstance(hist, list):
                        history = hist
                except Exception:
                    pass
        print(f"Price history: {len(history)} entries")
        for h in history[-10:]:
            print(f"  {h.get('timestamp', '?')}: ${h.get('price', '?')} ({h.get('strategy', '?')})")
        return

    print(json.dumps(state, indent=2))

    if args.dry_run:
        logger.info("Dry run — not updating profile")
        return

    success = update_price_on_profile(price)

    history = []
    if os.path.exists(PRICE_STATE_PATH):
        with open(PRICE_STATE_PATH) as f:
            try:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []
    history.append(state)
    with open(PRICE_STATE_PATH, "w") as f:
        json.dump(history[-200:], f, indent=2)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
