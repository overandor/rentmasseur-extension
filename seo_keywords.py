#!/usr/bin/env python3
"""SEO keyword research generator — produces keyword sets for each strategy.

Generates primary keywords, long-tail keywords, search volume estimates,
and content recommendations for SEO optimization.

Usage:
    python3 seo_keywords.py
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
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

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
SEO_DIR = os.path.join(CONTENT_DIR, "seo_keywords")

STRATEGIES = [
    "sensory_luxury", "therapeutic_expert", "mystery_desire", "local_hustle",
    "transformation_story", "night_owl", "athlete_recovery", "ceo_executive",
    "spiritual_healer", "traveler_companion", "medical_referral", "artist_soul",
    "discrete_confidential", "first_timer", "seasonal_special", "couples_duo",
    "bodybuilder_therapy", "yoga_fusion", "luxury_concierge", "recovery_addiction",
    "military_veteran", "lgbtq_pride", "senior_gentle", "office_relief",
    "dancer_flexibility", "meditation_guide", "hot_stone_specialist", "quick_lunch",
    "birthday_gift", "weekly_ritual",
]


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> Optional[str]:
    if not GROQ_API_KEY:
        logger.error("No GROQ_API_KEY")
        return None
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
                "temperature": 0.7,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("Groq API error: %s", e)
        return None


def main():
    os.makedirs(SEO_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    total = 0

    system_prompt = (
        "You are an SEO expert for massage therapy businesses in Manhattan, NYC. "
        "Generate keyword research in JSON format with: "
        "primary_keywords (array of 10), long_tail_keywords (array of 15), "
        "local_seo_keywords (array of 10 with NYC neighborhoods), "
        "content_recommendations (array of 5 blog post ideas), "
        "meta_description (150 chars), and "
        "title_tag (60 chars). "
        "Return ONLY valid JSON, no markdown."
    )

    all_keywords = {}

    for strategy in STRATEGIES:
        logger.info("Generating SEO keywords: %s", strategy)
        user_prompt = f"Generate SEO keyword research for strategy: {strategy}"
        result = _groq_chat(system_prompt, user_prompt, max_tokens=600)

        if result:
            try:
                if result.startswith("```"):
                    result = result.split("```")[1]
                    if result.startswith("json"):
                        result = result[4:]
                keywords = json.loads(result)
            except json.JSONDecodeError:
                keywords = {"raw": result}

            all_keywords[strategy] = keywords
            filepath = os.path.join(SEO_DIR, f"{today}_{strategy}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(keywords, f, indent=2)
            total += 1
            logger.info("Saved: %s", filepath)
        time.sleep(1)

    # Save combined file
    combined_path = os.path.join(SEO_DIR, f"{today}_all_strategies.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_keywords, f, indent=2)

    logger.info("=== Generated SEO keywords for %d strategies ===", total)
    print(json.dumps({"total_strategies": total, "date": today}, indent=2))


if __name__ == "__main__":
    main()
