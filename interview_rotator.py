#!/usr/bin/env python3
"""Interview rotator — generates and rotates interview Q&A sets on RentMasseur.

Generates fresh, hilarious interview questions and answers daily, rotates them
on the profile, and tracks which sets drive the most engagement via RL.

Usage:
    python3 interview_rotator.py                 # generate + rotate
    python3 interview_rotator.py --dry-run       # show next without uploading
    python3 interview_rotator.py --report        # show rotation history
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
INTERVIEWS_DIR = os.path.join(CONTENT_DIR, "interview_questions")
INTERVIEW_STATE_PATH = os.path.join(CONTENT_DIR, "interview_state.json")

INTERVIEW_ANGLES = [
    "funny_origin_story", "celebrity_encounter", "worst_client_story",
    "best_modality_debate", "myth_busting", "self_care_confession",
    "unusual_specialty", "travel_adventure", "philosophy_of_touch",
    "industry_secrets", "client_transformation", "funny_misunderstanding",
    "morning_routine", "guilty_pleasure", "proudest_moment",
    "biggest_mistake", "advice_for_newbies", "dream_client",
    "off_the_grid_life", "unexpected_skill",
]


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 1000, retries: int = 3) -> Optional[str]:
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


def generate_interview_set(angle: str) -> Optional[str]:
    system_prompt = (
        "You are a hilarious interview writer for a male massage therapist in Manhattan. "
        "Generate 10 interview Q&A that are FUNNY, engaging, and make clients want to CALL. "
        "The humor should be natural — witty, self-deprecating, playful. "
        "Each answer should subtly drive bookings. End with a CTA. "
        "Format: ## Q1: question? **A:** answer. Use markdown."
    )
    user_prompt = (
        f"Interview angle: {angle}\n"
        f"Write 10 hilarious interview questions with answers for a male masseur in Manhattan. "
        f"Make it memorable and phone-call-driving."
    )
    return _groq_chat(system_prompt, user_prompt, max_tokens=1500)


def main():
    parser = argparse.ArgumentParser(description="Interview rotator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    os.makedirs(INTERVIEWS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")

    if args.report:
        files = sorted(glob.glob(os.path.join(INTERVIEWS_DIR, "*.md")), reverse=True)
        print(f"Interview sets: {len(files)}")
        for f in files[:10]:
            print(f"  {os.path.basename(f)}: {os.path.getsize(f)} bytes")
        return

    angle = random.choice(INTERVIEW_ANGLES)
    logger.info("Generating interview set: %s", angle)

    content = generate_interview_set(angle)
    if not content:
        logger.error("Failed to generate interview")
        sys.exit(1)

    filepath = os.path.join(INTERVIEWS_DIR, f"{today}_{angle}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Saved: %s (%d chars)", filepath, len(content))

    print(json.dumps({
        "angle": angle,
        "chars": len(content),
        "file": filepath,
        "date": today,
    }, indent=2))


if __name__ == "__main__":
    main()
