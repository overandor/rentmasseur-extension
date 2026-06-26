#!/usr/bin/env python3
"""
Intent Router — uses Groq LLM to analyze context and rank the top bio strategies.
Returns the top N strategy names to run based on predicted client intent.
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("grpw", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# All 30 strategies with short descriptions for the LLM
ALL_STRATEGIES = [
    ("sensory_luxury", "Luxurious sensory experience, premium oils, candlelight, high-end clientele"),
    ("therapeutic_expert", "Clinical therapeutic massage, pain relief, certifications, back/neck focus"),
    ("mystery_desire", "Mysterious, alluring, teases the experience, curiosity-driven bookings"),
    ("local_hustle", "Manhattan local vibe, neighborhood energy, approachable, easy booking"),
    ("transformation_story", "Story-based, stress-to-relief transformation, emotional hook"),
    ("night_owl", "Late-night availability, after-hours, private evening sessions"),
    ("athlete_recovery", "Gym-goers, pre/post-workout, muscle recovery, sports performance"),
    ("ceo_executive", "Executive wellness, CEO/founder stress relief, time-efficient, premium"),
    ("spiritual_healer", "Holistic, energy work, chakras, mindfulness, breathwork"),
    ("traveler_companion", "Out-of-town visitors, jet lag, hotel-friendly, concierge service"),
    ("medical_referral", "Doctor-recommended, clinical back pain, sciatica, posture correction"),
    ("artist_soul", "Creative artistic approach, massage as art, intuitive touch"),
    ("discrete_confidential", "Absolute privacy, VIP clients, judgment-free, confidential studio"),
    ("first_timer", "Welcoming newcomers, gentle introduction, no experience needed"),
    ("seasonal_special", "Seasonal themes, winter warmth, summer cool-down, holiday stress"),
    ("couples_duo", "Couples, partners, duet sessions, romantic bonding experience"),
    ("bodybuilder_therapy", "Heavy lifters, deep pressure, fascia release, intense muscle work"),
    ("yoga_fusion", "Yoga + massage, stretching, flexibility, mind-body connection"),
    ("luxury_concierge", "White-glove in-home/hotel service, elite concierge, effortless booking"),
    ("recovery_addiction", "Sober wellness, recovery support, clean living, healthy coping"),
    ("military_veteran", "Veteran-friendly, service member respect, PT recovery, brotherhood"),
    ("lgbtq_pride", "Inclusive pride-forward, safe space, community, authentic expression"),
    ("senior_gentle", "Senior-friendly, gentle touch, mobility, arthritis, circulation"),
    ("office_relief", "Desk job recovery, neck pain, carpal tunnel, corporate warrior"),
    ("dancer_flexibility", "Dancers/performers, flexibility maintenance, injury prevention"),
    ("meditation_guide", "Guided meditation + massage, mindfulness, breath, tranquility"),
    ("hot_stone_specialist", "Hot stone specialty, heat therapy, deep relaxation, indulgence"),
    ("quick_lunch", "Express 30-45 min lunch-break massage, fast, effective, convenient"),
    ("birthday_gift", "Gift-worthy special occasion, treat yourself, memorable experience"),
    ("weekly_ritual", "Recurring weekly maintenance, body upkeep, long-term investment"),
]


def _build_context() -> str:
    """Build context string for the LLM router."""
    now = datetime.now()
    hour = now.hour
    time_of_day = "morning" if 6 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 22 else "late night"
    month = now.month
    season = "winter" if month in [12, 1, 2] else "spring" if month in [3, 4, 5] else "summer" if month in [6, 7, 8] else "fall"

    return (
        f"Current time: {now.strftime('%Y-%m-%d %H:%M')}. "
        f"Time of day: {time_of_day}. Season: {season}. "
        f"Location: Manhattan, NYC. "
        f"Target: professional masseur seeking maximum bookings and traffic."
    )


def route_intents(top_n: int = 5) -> List[str]:
    """Use Groq LLM to rank strategies and return top N names."""
    if not GROQ_API_KEY:
        logger.error("No GROQ_API_KEY for intent routing")
        # Fallback: return first N strategies
        return [s[0] for s in ALL_STRATEGIES[:top_n]]

    strategies_text = "\n".join([f"{i+1}. {name}: {desc}" for i, (name, desc) in enumerate(ALL_STRATEGIES)])
    context = _build_context()

    system_prompt = (
        "You are a marketing strategist for a masseur in Manhattan. "
        "Given the current context (time of day, season, location), analyze which bio angles "
        "would attract the most clients RIGHT NOW. Consider: who is most likely to book a massage "
        "at this specific time/season in NYC? Return ONLY a JSON array of the top strategy names."
    )

    user_prompt = (
        f"{context}\n\n"
        f"Available strategies:\n{strategies_text}\n\n"
        f"Task: Pick the {top_n} strategies most likely to convert clients RIGHT NOW. "
        f"Return ONLY a JSON array of strategy names (e.g., [\"local_hustle\", \"night_owl\", ...]). "
        f"No explanation, no markdown, just the JSON array."
    )

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
                "max_tokens": 200,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Extract JSON array from response
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            ranked = json.loads(match.group())
        else:
            ranked = json.loads(content)

        if not isinstance(ranked, list):
            raise ValueError("Response is not a list")

        # Validate strategy names
        valid_names = {s[0] for s in ALL_STRATEGIES}
        filtered = [name for name in ranked if name in valid_names]

        logger.info("Intent router selected top %d: %s", len(filtered), filtered)
        return filtered[:top_n] if filtered else [s[0] for s in ALL_STRATEGIES[:top_n]]

    except Exception as e:
        logger.error("Intent routing failed: %s", e)
        # Fallback
        return [s[0] for s in ALL_STRATEGIES[:top_n]]


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    top = route_intents(5)
    print(json.dumps(top, indent=2))
