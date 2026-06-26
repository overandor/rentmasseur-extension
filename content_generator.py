#!/usr/bin/env python3
"""Daily content generator for RentMasseur profile optimization.

Generates bios, blog posts, and interview questions using Groq LLM.
Runs mass analysis across all 30 strategies and collects the best versions.
Designed to run daily in CI/CD.

Usage:
    python3 content_generator.py                    # generate all content
    python3 content_generator.py --bios-only        # bios only
    python3 content_generator.py --blogs-only       # blog posts only
    python3 content_generator.py --questions-only   # interview questions only
"""

import argparse
import json
import os
import sys
import time
import hashlib
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
RENTMASSEUR_USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
BIOS_DIR = os.path.join(CONTENT_DIR, "bios")
BLOGS_DIR = os.path.join(CONTENT_DIR, "blog_posts")
QUESTIONS_DIR = os.path.join(CONTENT_DIR, "interview_questions")
HISTORY_FILE = os.path.join(CONTENT_DIR, "content_history.json")

STRATEGIES = [
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


def _ensure_dirs():
    for d in [CONTENT_DIR, BIOS_DIR, BLOGS_DIR, QUESTIONS_DIR]:
        os.makedirs(d, exist_ok=True)


def _load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(history: list):
    _ensure_dirs()
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2)
    except Exception as e:
        logger.warning("Failed to save history: %s", e)


def _content_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()[:12]


def _groq_chat(system_prompt: str, user_prompt: str, temperature: float = 0.9, max_tokens: int = 800, retries: int = 3) -> Optional[str]:
    if not GROQ_API_KEY:
        logger.error("No GROQ_API_KEY")
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
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=90,
            )
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                logger.warning("Groq rate limited, waiting %ds (attempt %d/%d)", wait, attempt + 1, retries)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
            return content
        except Exception as e:
            logger.error("Groq API error: %s", e)
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    return None


def _save_content(directory: str, strategy_name: str, content: str, ext: str = "md") -> str:
    ts = datetime.now().strftime("%Y%m%d")
    filename = f"{ts}_{strategy_name}.{ext}"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Saved: %s (%d chars)", filepath, len(content))
    return filepath


def generate_bios(history: list, used_hashes: set) -> list:
    logger.info("=== Generating bios for all 30 strategies ===")
    system_prompt = (
        "You are an elite copywriter for massage therapy profiles on RentMasseur. "
        "Each bio must be under 300 words, magnetic, SEO-friendly, and conversion-optimized. "
        "Avoid explicit content. Include keywords: massage, therapeutic, deep tissue, relaxation, session, Manhattan. "
        "CRITICAL: Every bio MUST end with a strong phone-call call-to-action like "
        "'Call now to book your session' or 'Pick up the phone and call me today'. "
        "The goal is MAXIMUM PHONE CALLS. Make the reader want to call immediately. "
        "Include urgency words: today, now, available, waiting, ready. "
        "Write ONLY the bio text."
    )
    results = []
    for strategy_name, strategy_desc in STRATEGIES:
        user_prompt = (
            f"Strategy: {strategy_name}\n"
            f"Description: {strategy_desc}\n"
            f"Write a compelling profile bio for a male masseur in Manhattan, NYC. "
            f"The bio MUST drive phone calls. End with a direct call-to-action "
            f"telling the reader to CALL NOW to book. No labels, no quotes, no explanation. Just the bio."
        )
        bio = _groq_chat(system_prompt, user_prompt)
        if bio:
            h = _content_hash(bio)
            if h in used_hashes:
                logger.info("Skip duplicate bio: %s", strategy_name)
                continue
            used_hashes.add(h)
            filepath = _save_content(BIOS_DIR, strategy_name, bio)
            results.append({
                "type": "bio",
                "strategy": strategy_name,
                "chars": len(bio),
                "hash": h,
                "file": filepath,
                "preview": bio[:120],
            })
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "bio",
                "strategy": strategy_name,
                "hash": h,
                "chars": len(bio),
            })
        time.sleep(1)
    logger.info("Generated %d bios", len(results))
    return results


def generate_blog_posts(history: list, used_hashes: set) -> list:
    logger.info("=== Generating blog posts for all 30 strategies ===")
    system_prompt = (
        "You are an expert content writer for a massage therapy blog. "
        "Write engaging, SEO-optimized blog posts (500-800 words) that attract clients. "
        "Include a compelling title, subheadings, and a call-to-action. "
        "Avoid explicit content. Use markdown formatting."
    )
    results = []
    for strategy_name, strategy_desc in STRATEGIES:
        user_prompt = (
            f"Strategy: {strategy_name}\n"
            f"Angle: {strategy_desc}\n"
            f"Write a blog post for a male masseur in Manhattan, NYC. "
            f"The post should be informative, engaging, and drive bookings. "
            f"Use markdown with a # title, ## subheadings, and a CTA at the end."
        )
        post = _groq_chat(system_prompt, user_prompt, max_tokens=1200)
        if post:
            h = _content_hash(post)
            if h in used_hashes:
                logger.info("Skip duplicate blog: %s", strategy_name)
                continue
            used_hashes.add(h)
            filepath = _save_content(BLOGS_DIR, strategy_name, post)
            results.append({
                "type": "blog_post",
                "strategy": strategy_name,
                "chars": len(post),
                "hash": h,
                "file": filepath,
                "preview": post[:120],
            })
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "blog_post",
                "strategy": strategy_name,
                "hash": h,
                "chars": len(post),
            })
        time.sleep(1)
    logger.info("Generated %d blog posts", len(results))
    return results


def generate_interview_questions(history: list, used_hashes: set) -> list:
    logger.info("=== Generating interview questions for all 30 strategies ===")
    system_prompt = (
        "You are an interview coach for massage therapists. "
        "Generate 10 insightful interview questions that a journalist or blogger "
        "would ask a male masseur, based on the given strategy angle. "
        "Also include suggested answers that are professional, engaging, and on-brand. "
        "Use markdown formatting with numbered questions and bullet-point answers."
    )
    results = []
    for strategy_name, strategy_desc in STRATEGIES:
        user_prompt = (
            f"Strategy: {strategy_name}\n"
            f"Angle: {strategy_desc}\n"
            f"Generate 10 interview questions with suggested answers for a male masseur "
            f"in Manhattan, NYC. Make the answers compelling and booking-oriented. "
            f"Format: ## Q1: question? followed by **A:** answer."
        )
        questions = _groq_chat(system_prompt, user_prompt, max_tokens=1500)
        if questions:
            h = _content_hash(questions)
            if h in used_hashes:
                logger.info("Skip duplicate questions: %s", strategy_name)
                continue
            used_hashes.add(h)
            filepath = _save_content(QUESTIONS_DIR, strategy_name, questions)
            results.append({
                "type": "interview_questions",
                "strategy": strategy_name,
                "chars": len(questions),
                "hash": h,
                "file": filepath,
                "preview": questions[:120],
            })
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "interview_questions",
                "strategy": strategy_name,
                "hash": h,
                "chars": len(questions),
            })
        time.sleep(1)
    logger.info("Generated %d interview question sets", len(results))
    return results


def generate_mass_analysis(bios: list, blogs: list, questions: list) -> Optional[str]:
    logger.info("=== Running mass analysis across all generated content ===")
    system_prompt = (
        "You are a marketing analyst and content strategist. "
        "Analyze the generated bios, blog posts, and interview questions across all strategies. "
        "Produce a comprehensive report with: "
        "1. Top 5 bios ranked by conversion potential "
        "2. Top 5 blog posts ranked by SEO and engagement potential "
        "3. Top 5 interview question sets ranked by PR value "
        "4. Cross-strategy themes that perform best "
        "5. Recommended posting schedule for the week "
        "6. Best bio to use on the profile right now "
        "Use markdown formatting."
    )

    bios_summary = "\n".join([f"- {b['strategy']} ({b['chars']} chars): {b['preview']}..." for b in bios])
    blogs_summary = "\n".join([f"- {b['strategy']} ({b['chars']} chars): {b['preview']}..." for b in blogs])
    questions_summary = "\n".join([f"- {q['strategy']} ({q['chars']} chars): {q['preview']}..." for q in questions])

    user_prompt = (
        f"Today's generated content:\n\n"
        f"## Bios ({len(bios)} generated):\n{bios_summary}\n\n"
        f"## Blog Posts ({len(blogs)} generated):\n{blogs_summary}\n\n"
        f"## Interview Questions ({len(questions)} generated):\n{questions_summary}\n\n"
        f"Produce the mass analysis report."
    )

    analysis = _groq_chat(system_prompt, user_prompt, temperature=0.7, max_tokens=2000)
    if analysis:
        ts = datetime.now().strftime("%Y%m%d")
        filepath = os.path.join(CONTENT_DIR, f"mass_analysis_{ts}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(analysis)
        logger.info("Mass analysis saved: %s (%d chars)", filepath, len(analysis))
        return filepath
    return None


def main():
    parser = argparse.ArgumentParser(description="Daily content generator for RentMasseur")
    parser.add_argument("--bios-only", action="store_true")
    parser.add_argument("--blogs-only", action="store_true")
    parser.add_argument("--questions-only", action="store_true")
    parser.add_argument("--no-analysis", action="store_true", help="Skip mass analysis")
    args = parser.parse_args()

    _ensure_dirs()
    history = _load_history()
    used_hashes = {entry.get("hash", "") for entry in history}

    all_bios = []
    all_blogs = []
    all_questions = []

    if not args.blogs_only and not args.questions_only:
        all_bios = generate_bios(history, used_hashes)
    if not args.bios_only and not args.questions_only:
        all_blogs = generate_blog_posts(history, used_hashes)
    if not args.bios_only and not args.blogs_only:
        all_questions = generate_interview_questions(history, used_hashes)

    if not args.no_analysis and (all_bios or all_blogs or all_questions):
        generate_mass_analysis(all_bios, all_blogs, all_questions)

    _save_history(history)

    summary = {
        "date": datetime.now(timezone.utc).isoformat(),
        "bios_generated": len(all_bios),
        "blog_posts_generated": len(all_blogs),
        "interview_questions_generated": len(all_questions),
        "total_strategies": len(STRATEGIES),
    }
    summary_path = os.path.join(CONTENT_DIR, "daily_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("=== Daily content generation complete ===")
    logger.info("Bios: %d | Blog posts: %d | Interview questions: %d",
                len(all_bios), len(all_blogs), len(all_questions))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
