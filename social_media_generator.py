#!/usr/bin/env python3
"""Social media post generator — creates platform-specific posts from daily content.

Generates posts for Twitter/X, Instagram, Facebook, and LinkedIn based on
the daily bios, blog posts, and interview questions.

Usage:
    python3 social_media_generator.py
    python3 social_media_generator.py --platform twitter
"""

import argparse
import json
import os
import sys
import glob
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
SOCIAL_DIR = os.path.join(CONTENT_DIR, "social_posts")

PLATFORMS = {
    "twitter": {"max_chars": 280, "style": "concise, punchy, with hashtags"},
    "instagram": {"max_chars": 2200, "style": "visual, emoji-rich, story-driven, with hashtags"},
    "facebook": {"max_chars": 5000, "style": "conversational, community-focused, engaging"},
    "linkedin": {"max_chars": 3000, "style": "professional, thought-leadership, industry-focused"},
}

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


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> Optional[str]:
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
                "temperature": 0.9,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("Groq API error: %s", e)
        return None


def generate_social_posts(platform: str, strategy: str) -> Optional[str]:
    """Generate social media posts for a specific platform and strategy."""
    config = PLATFORMS[platform]
    system_prompt = (
        f"You are a social media manager for a male massage therapist in Manhattan, NYC. "
        f"Create a {platform} post that is {config['style']}. "
        f"Maximum {config['max_chars']} characters. "
        f"Avoid explicit content. Include relevant hashtags. "
        f"Drive bookings to the RentMasseur profile. Write ONLY the post text."
    )
    user_prompt = (
        f"Strategy angle: {strategy}\n"
        f"Create a compelling {platform} post for a massage therapist. "
        f"Make it engaging and booking-oriented."
    )
    return _groq_chat(system_prompt, user_prompt)


def main():
    parser = argparse.ArgumentParser(description="Generate social media posts from daily content")
    parser.add_argument("--platform", choices=list(PLATFORMS.keys()), help="Generate for specific platform only")
    parser.add_argument("--strategies", nargs="*", default=STRATEGIES, help="Strategies to generate for")
    args = parser.parse_args()

    os.makedirs(SOCIAL_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    platforms = [args.platform] if args.platform else list(PLATFORMS.keys())
    total = 0

    for platform in platforms:
        platform_dir = os.path.join(SOCIAL_DIR, platform)
        os.makedirs(platform_dir, exist_ok=True)
        logger.info("=== Generating %s posts ===", platform)

        for strategy in args.strategies:
            post = generate_social_posts(platform, strategy)
            if post:
                filepath = os.path.join(platform_dir, f"{today}_{strategy}.md")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(post)
                total += 1
                logger.info("%s/%s: %d chars", platform, strategy, len(post))
            time.sleep(0.5)

    logger.info("=== Generated %d social media posts ===", total)
    print(json.dumps({"total_posts": total, "platforms": platforms, "date": today}, indent=2))


if __name__ == "__main__":
    main()
