#!/usr/bin/env python3
"""Weekly report generator — compiles performance and content summary.

Generates a comprehensive weekly report covering:
- Content generated (bios, blogs, questions, social, emails, SEO)
- Availability keeper run history
- Competitor analysis summary
- Top performing strategies
- Recommendations for next week

Usage:
    python3 weekly_report.py
    python3 weekly_report.py --output content/weekly_report.md
"""

import json
import os
import sys
import glob
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

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> Optional[str]:
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
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("Groq API error: %s", e)
        return None


def collect_weekly_stats() -> dict:
    """Collect stats for the past 7 days."""
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    date_prefixes = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

    stats = {
        "period": f"{week_ago.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
        "bios": 0,
        "blog_posts": 0,
        "interview_questions": 0,
        "social_posts": 0,
        "email_templates": 0,
        "seo_keywords": 0,
        "mass_analyses": 0,
        "competitor_data": False,
        "strategies_covered": set(),
    }

    for subdir, key in [
        ("bios", "bios"),
        ("blog_posts", "blog_posts"),
        ("interview_questions", "interview_questions"),
        ("social_posts", "social_posts"),
        ("email_templates", "email_templates"),
        ("seo_keywords", "seo_keywords"),
    ]:
        directory = os.path.join(CONTENT_DIR, subdir)
        if os.path.exists(directory):
            ext = "json" if key == "seo_keywords" else "md"
            for dp in date_prefixes:
                files = glob.glob(os.path.join(directory, f"{dp}_*.{ext}"))
                stats[key] += len(files)
                for f in files:
                    basename = os.path.basename(f)
                    if "_" in basename:
                        strategy = basename.split("_", 1)[1].rsplit(".", 1)[0]
                        stats["strategies_covered"].add(strategy)

    # Mass analyses
    for dp in date_prefixes:
        analyses = glob.glob(os.path.join(CONTENT_DIR, f"mass_analysis_{dp}.md"))
        stats["mass_analyses"] += len(analyses)

    # Competitor data
    competitor_path = os.path.join(CONTENT_DIR, "competitor_data.json")
    stats["competitor_data"] = os.path.exists(competitor_path)

    stats["strategies_covered"] = list(sorted(stats["strategies_covered"]))
    return stats


def generate_report(stats: dict) -> str:
    """Generate the weekly report using Groq."""
    system_prompt = (
        "You are a marketing analyst for a massage therapy business in Manhattan, NYC. "
        "Generate a comprehensive weekly report in markdown format. "
        "Include: executive summary, content production metrics, strategy coverage, "
        "recommendations for next week, and action items. "
        "Be specific and data-driven."
    )

    user_prompt = (
        f"Weekly Stats:\n{json.dumps(stats, indent=2)}\n\n"
        f"Generate the weekly report."
    )

    report = _groq_chat(system_prompt, user_prompt)
    if not report:
        report = f"# Weekly Report — {stats['period']}\n\n## Stats\n\n```json\n{json.dumps(stats, indent=2)}\n```"
    return report


def main():
    output_path = os.path.join(CONTENT_DIR, f"weekly_report_{datetime.now().strftime('%Y%m%d')}.md")
    os.makedirs(CONTENT_DIR, exist_ok=True)

    logger.info("Collecting weekly stats...")
    stats = collect_weekly_stats()
    logger.info("Stats: %s", json.dumps({k: v for k, v in stats.items() if k != "strategies_covered"}, indent=2))

    logger.info("Generating report with Groq...")
    report = generate_report(stats)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("Report saved: %s (%d chars)", output_path, len(report))

    print(f"\nReport: {output_path}")
    print(f"Strategies covered: {len(stats['strategies_covered'])}")
    print(f"Total content: {sum(v for k, v in stats.items() if isinstance(v, int))}")


if __name__ == "__main__":
    main()
