#!/usr/bin/env python3
"""Reinforcement Learning feedback loop for RentMasseur profile optimization.

Tracks profile views, email clicks, phone calls, and booking inquiries per bio variant.
Uses reward signals to decide which bios to keep, retire, or promote.

Reward function:
  reward = (views * 1) + (email_clicks * 5) + (phone_clicks * 10) + (bookings * 50)
  penalty = (bio_age_days * -0.5)  # stale bios decay

The system scrapes profile stats from RentMasseur, correlates them to the active bio,
and updates the RL state. Bios that underperform are retired. Top performers are reused
and mutated by the LLM for variation.

Usage:
    python3 rl_feedback.py                    # collect stats and update rewards
    python3 rl_feedback.py --report           # show reward history
    python3 rl_feedback.py --reset            # reset RL state
"""

import argparse
import json
import os
import sys
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("grpw", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
RENTMASSEUR_USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
RENTMASSEUR_PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
RL_STATE_PATH = os.path.join(CONTENT_DIR, "rl_state.json")
RL_HISTORY_PATH = os.path.join(CONTENT_DIR, "rl_history.json")
PROFILE_URL = "https://rentmasseur.com/settings/stats"
DASHBOARD_URL = "https://rentmasseur.com/dashboard"

REWARD_WEIGHTS = {
    "views": 1,
    "email_clicks": 5,
    "phone_clicks": 10,
    "booking_inquiries": 50,
    "favorites": 3,
    "messages": 8,
}


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 800, retries: int = 3) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.9,
                    "max_tokens": max_tokens,
                },
                timeout=90,
            )
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    return None


def _groq_json(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> Optional[dict]:
    raw = _groq_chat(system_prompt, user_prompt, max_tokens=max_tokens)
    if not raw:
        return None
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _load_rl_state() -> dict:
    if os.path.exists(RL_STATE_PATH):
        try:
            with open(RL_STATE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "bios": {},
        "current_bio_id": None,
        "current_bio_start": None,
        "total_rotations": 0,
        "best_bio_id": None,
        "best_reward": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_rl_state(state: dict):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    with open(RL_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _load_history() -> list:
    if os.path.exists(RL_HISTORY_PATH):
        try:
            with open(RL_HISTORY_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(history: list):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    with open(RL_HISTORY_PATH, "w") as f:
        json.dump(history[-500:], f, indent=2)


def scrape_profile_stats() -> dict:
    """Scrape profile view/click stats from RentMasseur dashboard."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

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
            from rentmasseur_core import login
            if not login(driver):
                logger.error("Login failed for stats scraping")
                return {}

            driver.get(DASHBOARD_URL)
            time.sleep(5)

            stats = {
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "views": 0,
                "email_clicks": 0,
                "phone_clicks": 0,
                "booking_inquiries": 0,
                "favorites": 0,
                "messages": 0,
            }

            page_text = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
            page_html = driver.execute_script("return document.documentElement ? document.documentElement.outerHTML : '';") or ""

            import re
            patterns = {
                "views": [r"(\d+)\s*(?:profile\s*)?views?", r"views?:\s*(\d+)", r"(\d+)\s*views"],
                "email_clicks": [r"(\d+)\s*email\s*(?:clicks?|opens?)", r"email:\s*(\d+)", r"(\d+)\s*email"],
                "phone_clicks": [r"(\d+)\s*phone\s*(?:clicks?|calls?)", r"phone:\s*(\d+)", r"(\d+)\s*phone"],
                "booking_inquiries": [r"(\d+)\s*(?:booking|inquir|appoint)", r"bookings?:\s*(\d+)"],
                "favorites": [r"(\d+)\s*(?:favorit|likes?|saves?)", r"favorites?:\s*(\d+)"],
                "messages": [r"(\d+)\s*messages?", r"messages?:\s*(\d+)"],
            }

            for key, patterns_list in patterns.items():
                for pattern in patterns_list:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        stats[key] = int(match.group(1))
                        break

            logger.info("Scraped stats: %s", json.dumps(stats))
            return stats

        finally:
            driver.quit()
    except Exception as e:
        logger.error("Stats scraping error: %s", e)
        return {}


def calculate_reward(stats: dict, bio_age_days: float) -> float:
    """Calculate reward score from stats."""
    reward = 0
    for key, weight in REWARD_WEIGHTS.items():
        reward += stats.get(key, 0) * weight
    reward -= bio_age_days * 0.5  # stale bio penalty
    return round(reward, 2)


def update_rl_state(stats: dict) -> dict:
    """Update RL state with new stats and calculate reward for current bio."""
    state = _load_rl_state()
    current_bio_id = state.get("current_bio_id")

    if not current_bio_id:
        logger.warning("No current bio ID in RL state — nothing to reward")
        return state

    bio_entry = state["bios"].get(current_bio_id, {})
    previous_stats = bio_entry.get("last_stats", {})
    bio_start = state.get("current_bio_start")

    if bio_start:
        bio_age = (datetime.now(timezone.utc) - datetime.fromisoformat(bio_start)).total_seconds() / 86400
    else:
        bio_age = 0

    # Delta stats (new since last check)
    delta = {key: max(0, stats.get(key, 0) - previous_stats.get(key, 0)) for key in REWARD_WEIGHTS}
    delta_reward = calculate_reward(delta, bio_age)

    # Update bio entry
    bio_entry["last_stats"] = stats
    bio_entry["total_reward"] = bio_entry.get("total_reward", 0) + delta_reward
    bio_entry["delta_reward"] = delta_reward
    bio_entry["delta_stats"] = delta
    bio_entry["last_updated"] = datetime.now(timezone.utc).isoformat()
    bio_entry["age_days"] = round(bio_age, 2)
    state["bios"][current_bio_id] = bio_entry

    # Track best bio
    if bio_entry["total_reward"] > state.get("best_reward", 0):
        state["best_bio_id"] = current_bio_id
        state["best_reward"] = bio_entry["total_reward"]

    # Log to history
    history = _load_history()
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bio_id": current_bio_id,
        "delta_stats": delta,
        "delta_reward": delta_reward,
        "total_reward": bio_entry["total_reward"],
        "bio_age_days": round(bio_age, 2),
    })
    _save_history(history)

    logger.info("Bio %s: delta_reward=%.2f, total_reward=%.2f (age: %.1f days)",
                current_bio_id, delta_reward, bio_entry["total_reward"], bio_age)

    # Decision: should we rotate?
    should_rotate = False
    reason = ""

    if bio_age >= 3.0:
        should_rotate = True
        reason = "bio_age >= 3 days"
    elif bio_age >= 1.0 and delta_reward < 5:
        should_rotate = True
        reason = "low reward (delta < 5 in 1+ day)"
    elif bio_age >= 0.5 and delta_reward == 0 and sum(delta.values()) == 0:
        should_rotate = True
        reason = "zero engagement in 12+ hours"

    state["should_rotate"] = should_rotate
    state["rotate_reason"] = reason

    if should_rotate:
        logger.info("Rotation triggered: %s", reason)

    _save_rl_state(state)
    return state


def register_new_bio(bio_id: str, bio_text: str, strategy: str, source: str = "generated"):
    """Register a new bio in the RL state."""
    state = _load_rl_state()

    # Finalize previous bio
    prev_id = state.get("current_bio_id")
    if prev_id and prev_id in state.get("bios", {}):
        state["bios"][prev_id]["end_time"] = datetime.now(timezone.utc).isoformat()

    state["current_bio_id"] = bio_id
    state["current_bio_start"] = datetime.now(timezone.utc).isoformat()
    state["total_rotations"] = state.get("total_rotations", 0) + 1

    state["bios"][bio_id] = {
        "bio_text": bio_text[:500],
        "strategy": strategy,
        "source": source,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "total_reward": 0,
        "delta_reward": 0,
        "last_stats": {},
        "age_days": 0,
    }

    _save_rl_state(state)
    logger.info("Registered new bio: %s (strategy: %s, rotation #%d)",
                bio_id, strategy, state["total_rotations"])


def get_top_performing_bios(n: int = 5) -> list:
    """Get top N performing bios by reward."""
    state = _load_rl_state()
    bios = state.get("bios", {})
    sorted_bios = sorted(bios.items(), key=lambda x: x[1].get("total_reward", 0), reverse=True)
    return sorted_bios[:n]


def get_retired_bios() -> list:
    """Get bios that should be retired (low reward)."""
    state = _load_rl_state()
    bios = state.get("bios", {})
    retired = []
    for bio_id, data in bios.items():
        if data.get("total_reward", 0) < 0 and bio_id != state.get("current_bio_id"):
            retired.append(bio_id)
    return retired


def generate_mutated_bio(top_bio_text: str, strategy: str) -> Optional[str]:
    """Generate a mutated version of a top-performing bio using LLM."""
    system_prompt = (
        "You are a hilarious, magnetic copywriter for RentMasseur. "
        "Take the given top-performing bio and create a FUNNIER, MORE COMPELLING version. "
        "Rules:\n"
        "1. Keep what works (CTA, urgency, keywords) but make it FUNNIER\n"
        "2. Add humor — clients call masseurs who make them smile\n"
        "3. Must still drive PHONE CALLS — end with 'Call me now'\n"
        "4. Under 250 words\n"
        "5. No explicit content\n"
        "6. Be memorable — stand out from every boring masseur bio\n"
        "Write ONLY the bio text."
    )
    user_prompt = (
        f"Top-performing bio (reward: high):\n{top_bio_text}\n\n"
        f"Strategy: {strategy}\n"
        f"Make it HILARIOUS and even more phone-call-driving. Mutate it."
    )
    return _groq_chat(system_prompt, user_prompt, max_tokens=600)


def generate_hilarious_bio(strategy: str, strategy_desc: str, context: str = "") -> Optional[str]:
    """Generate a hilarious, phone-call-driving bio."""
    system_prompt = (
        "You are the funniest, most magnetic copywriter on RentMasseur. "
        "Write bios that make clients LAUGH and then CALL. "
        "Rules:\n"
        "1. Be genuinely funny — not cringe, not try-hard, naturally hilarious\n"
        "2. Humor styles: self-deprecating, witty observations, playful exaggeration\n"
        "3. MUST end with a phone-call CTA: 'Call me now' or 'Pick up the phone'\n"
        "4. Include urgency: 'available now', 'today', 'don't wait'\n"
        "5. SEO keywords: massage, Manhattan, deep tissue, therapeutic\n"
        "6. Under 250 words\n"
        "7. No explicit content\n"
        "8. Make them remember you and CALL\n"
        "Write ONLY the bio text."
    )
    user_prompt = (
        f"Strategy: {strategy}\n"
        f"Angle: {strategy_desc}\n"
        f"Context: {context}\n"
        f"Write the funniest, most phone-call-driving bio ever for a male masseur in Manhattan."
    )
    return _groq_chat(system_prompt, user_prompt, max_tokens=600)


def report() -> str:
    """Generate a human-readable RL report."""
    state = _load_rl_state()
    history = _load_history()

    lines = ["=" * 60, "RL FEEDBACK REPORT", "=" * 60]
    lines.append(f"Total rotations: {state.get('total_rotations', 0)}")
    lines.append(f"Current bio: {state.get('current_bio_id', 'none')}")
    lines.append(f"Best bio: {state.get('best_bio_id', 'none')} (reward: {state.get('best_reward', 0)})")
    lines.append("")

    lines.append("TOP 5 PERFORMING BIOS:")
    for bio_id, data in get_top_performing_bios(5):
        lines.append(f"  {bio_id}: reward={data.get('total_reward', 0)}, "
                      f"strategy={data.get('strategy', '?')}, "
                      f"age={data.get('age_days', 0)}d")

    lines.append("")
    lines.append(f"History entries: {len(history)}")
    if history:
        recent = history[-5:]
        lines.append("RECENT REWARDS:")
        for h in recent:
            lines.append(f"  {h['timestamp']}: bio={h['bio_id']}, "
                          f"delta={h['delta_reward']}, total={h['total_reward']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RL feedback loop for RentMasseur")
    parser.add_argument("--report", action="store_true", help="Show RL report")
    parser.add_argument("--reset", action="store_true", help="Reset RL state")
    parser.add_argument("--collect", action="store_true", help="Collect stats and update rewards")
    args = parser.parse_args()

    if args.reset:
        _save_rl_state({"bios": {}, "current_bio_id": None, "total_rotations": 0, "created_at": datetime.now(timezone.utc).isoformat()})
        logger.info("RL state reset")
        return

    if args.report:
        print(report())
        return

    # Default: collect stats
    logger.info("Collecting profile stats...")
    stats = scrape_profile_stats()
    if not stats:
        logger.error("Failed to collect stats")
        sys.exit(1)

    state = update_rl_state(stats)
    print(json.dumps({
        "stats": stats,
        "should_rotate": state.get("should_rotate", False),
        "rotate_reason": state.get("rotate_reason", ""),
        "current_bio": state.get("current_bio_id"),
        "total_reward": state["bios"].get(state.get("current_bio_id", ""), {}).get("total_reward", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
