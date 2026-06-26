#!/usr/bin/env python3
"""Blog rotator — generates and rotates blog posts on RentMasseur profile.

Generates fresh, SEO-optimized, hilarious blog posts daily and rotates them.
Tracks engagement via RL feedback to determine which posts drive bookings.

Usage:
    python3 blog_rotator.py                 # generate + pick next blog
    python3 blog_rotator.py --dry-run       # show without uploading
    python3 blog_rotator.py --report        # show blog history
"""

import argparse
import json
import os
import sys
import time
import random
import glob
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
BLOGS_DIR = os.path.join(CONTENT_DIR, "blog_posts")

BLOG_TOPICS = [
    "why_i_became_a_masseur", "funniest_client_requests", "deep_tissue_vs_swedish",
    "what_your_body_is_telling_you", "midnight_massage_stories", "the_art_of_touch",
    "recovering_from_desk_death", "manhattan_stress_epidemic", "gym_bro_recovery_guide",
    "why_you_should_call_right_now", "massage_myths_busted", "my_weirdest_session",
    "self_care_isnt_selfish", "the_perfect_session", "what_clients_get_wrong",
    "seasonal_stress_survival", "couples_massage_etiquette", "first_time_jitters",
    "the_science_of_relaxation", "why_price_doesnt_equal_value",
]


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 1200, retries: int = 3) -> Optional[str]:
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
                    "temperature": 0.95,
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


def generate_blog_post(topic: str) -> Optional[str]:
    system_prompt = (
        "You are a hilarious, SEO-optimized blog writer for a male massage therapist in Manhattan. "
        "Write engaging blog posts (500-800 words) that are FUNNY and drive PHONE CALLS. "
        "Include a compelling title, subheadings, and a strong CTA: 'Call me now to book'. "
        "Use markdown. Be memorable. No explicit content."
    )
    user_prompt = (
        f"Blog topic: {topic}\n"
        f"Write the funniest, most engaging blog post about this topic for a Manhattan masseur. "
        f"Make readers laugh and then CALL to book."
    )
    return _groq_chat(system_prompt, user_prompt, max_tokens=1200)


def main():
    parser = argparse.ArgumentParser(description="Blog rotator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    os.makedirs(BLOGS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")

    if args.report:
        files = sorted(glob.glob(os.path.join(BLOGS_DIR, "*.md")), reverse=True)
        print(f"Blog posts: {len(files)}")
        for f in files[:10]:
            print(f"  {os.path.basename(f)}: {os.path.getsize(f)} bytes")
        return

    topic = random.choice(BLOG_TOPICS)
    logger.info("Generating blog post: %s", topic)

    content = generate_blog_post(topic)
    if not content:
        logger.error("Failed to generate blog post")
        sys.exit(1)

    filepath = os.path.join(BLOGS_DIR, f"{today}_{topic}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Saved: %s (%d chars)", filepath, len(content))

    print(json.dumps({
        "topic": topic,
        "chars": len(content),
        "file": filepath,
        "date": today,
    }, indent=2))


if __name__ == "__main__":
    main()
