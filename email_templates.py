#!/usr/bin/env python3
"""Email template generator — creates booking-related email templates.

Generates: booking confirmation, follow-up, rebooking reminder,
thank you, and seasonal promotion emails.

Usage:
    python3 email_templates.py
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
EMAIL_DIR = os.path.join(CONTENT_DIR, "email_templates")

EMAIL_TYPES = [
    ("booking_confirmation", "Sent immediately after a client books a session. Include date/time confirmation, what to expect, and preparation tips."),
    ("follow_up", "Sent 2 hours after the session. Ask for feedback, offer rebooking discount, and thank them."),
    ("rebooking_reminder", "Sent 2 weeks after last session. Remind them of benefits of regular massage, offer a loyalty discount."),
    ("thank_you", "Sent 1 day after first session. Welcome them as a new client, share tips, and invite to book again."),
    ("seasonal_promotion", "Sent seasonally. Offer a seasonal special (winter warmth, summer recovery, holiday stress relief)."),
    ("no_show_followup", "Sent after a missed appointment. Polite, understanding, and offers easy rescheduling."),
    ("birthday_gift", "Sent as a promotional email. Position massage as the perfect gift for self or others."),
    ("newsletter_monthly", "Monthly newsletter with wellness tips, self-care advice, and booking link."),
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
                "temperature": 0.8,
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
    os.makedirs(EMAIL_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    total = 0

    system_prompt = (
        "You are an expert email copywriter for a male massage therapist in Manhattan, NYC. "
        "Write professional, warm, and conversion-optimized emails. "
        "Include a subject line, greeting, body, and signature. "
        "Use [CLIENT_NAME] and [THERAPIST_NAME] as placeholders. "
        "Avoid explicit content. Format as markdown."
    )

    for email_type, description in EMAIL_TYPES:
        logger.info("Generating: %s", email_type)
        user_prompt = (
            f"Email type: {email_type}\n"
            f"Description: {description}\n"
            f"Write the email template. Include subject line."
        )
        email = _groq_chat(system_prompt, user_prompt, max_tokens=600)
        if email:
            filepath = os.path.join(EMAIL_DIR, f"{today}_{email_type}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(email)
            total += 1
            logger.info("Saved: %s (%d chars)", filepath, len(email))
        time.sleep(1)

    logger.info("=== Generated %d email templates ===", total)
    print(json.dumps({"total_emails": total, "date": today}, indent=2))


if __name__ == "__main__":
    main()
