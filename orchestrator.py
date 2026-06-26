#!/usr/bin/env python3
"""Master orchestrator for RentMasseur dynamic optimization.

Runs the full autonomous loop:
1. RL feedback collection (views, clicks, calls)
2. Bio rotation (A/B tested, hilarious, phone-call optimized)
3. Photo rotation
4. Price rotation
5. Interview rotation
6. Blog rotation
7. Data collection and correlation
8. Performance optimization

Usage:
    python3 orchestrator.py --all       # run all rotations
    python3 orchestrator.py --bio       # rotate bio only
    python3 orchestrator.py --stats     # collect stats only
    python3 orchestrator.py --report      # show performance report
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
ORCHESTRATOR_LOG = os.path.join(CONTENT_DIR, "orchestrator.log")

# Reward weights for RL
REWARD_WEIGHTS = {
    "views": 1,
    "email_clicks": 5,
    "phone_clicks": 10,
    "booking_inquiries": 50,
    "favorites": 3,
    "messages": 8,
}

# Rotation rules: max_age_hours, min_reward_threshold
ROTATION_RULES = {
    "bio": (24, 5),
    "photo": (48, 3),
    "price": (12, 8),
    "interview": (72, 2),
    "blog": (48, 4),
}


def log_event(event: dict):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with open(ORCHESTRATOR_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def collect_stats() -> dict:
    """Run rl_feedback.py to collect profile stats."""
    logger.info("=== Collecting RL stats ===")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "rl_feedback.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            logger.info("Stats collected successfully")
        else:
            logger.warning("Stats collection returned non-zero: %s", result.stderr)
        # Try to parse stats from output
        try:
            lines = result.stdout.split("\n")
            for line in lines:
                if line.strip().startswith("{"):
                    return json.loads(line)
        except Exception:
            pass
    except Exception as e:
        logger.error("Stats collection failed: %s", e)
    return {}


def run_bio_rotation(dry_run: bool = False) -> bool:
    """Run A/B tested bio rotation."""
    logger.info("=== Rotating bio (A/B tested, hilarious) ===")
    try:
        import subprocess
        cmd = ["python3", "bio_ab_tester.py"]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("Bio rotation completed")
            log_event({"component": "bio", "status": "success", "stdout": result.stdout[-500:]})
            return True
        logger.warning("Bio rotation failed: %s", result.stderr[-500:])
        log_event({"component": "bio", "status": "failed", "stderr": result.stderr[-500:]})
        return False
    except Exception as e:
        logger.error("Bio rotation error: %s", e)
        log_event({"component": "bio", "status": "error", "error": str(e)})
        return False


def run_photo_rotation(dry_run: bool = False) -> bool:
    logger.info("=== Rotating photo ===")
    try:
        import subprocess
        cmd = ["python3", "photo_rotator.py"]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        success = result.returncode == 0
        log_event({"component": "photo", "status": "success" if success else "failed"})
        return success
    except Exception as e:
        log_event({"component": "photo", "status": "error", "error": str(e)})
        return False


def run_price_rotation(dry_run: bool = False) -> bool:
    logger.info("=== Rotating price ===")
    try:
        import subprocess
        cmd = ["python3", "price_rotator.py"]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        success = result.returncode == 0
        log_event({"component": "price", "status": "success" if success else "failed"})
        return success
    except Exception as e:
        log_event({"component": "price", "status": "error", "error": str(e)})
        return False


def run_interview_rotation(dry_run: bool = False) -> bool:
    logger.info("=== Rotating interview ===")
    try:
        import subprocess
        cmd = ["python3", "interview_rotator.py"]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        success = result.returncode == 0
        log_event({"component": "interview", "status": "success" if success else "failed"})
        return success
    except Exception as e:
        log_event({"component": "interview", "status": "error", "error": str(e)})
        return False


def run_blog_rotation(dry_run: bool = False) -> bool:
    logger.info("=== Rotating blog ===")
    try:
        import subprocess
        cmd = ["python3", "blog_rotator.py"]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=180,
        )
        success = result.returncode == 0
        log_event({"component": "blog", "status": "success" if success else "failed"})
        return success
    except Exception as e:
        log_event({"component": "blog", "status": "error", "error": str(e)})
        return False


def generate_daily_content() -> bool:
    """Run the full daily content generator."""
    logger.info("=== Generating daily content ===")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "content_generator.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=600,
        )
        success = result.returncode == 0
        log_event({"component": "content_generator", "status": "success" if success else "failed"})
        return success
    except Exception as e:
        log_event({"component": "content_generator", "status": "error", "error": str(e)})
        return False


def master_report() -> str:
    """Generate master performance report."""
    lines = ["=" * 60, "RENTMASSEUR AUTONOMOUS ORCHESTRATOR REPORT", "=" * 60]

    # RL state
    if os.path.exists(os.path.join(CONTENT_DIR, "rl_state.json")):
        try:
            with open(os.path.join(CONTENT_DIR, "rl_state.json")) as f:
                rl = json.load(f)
            lines.append(f"\nCurrent bio: {rl.get('current_bio_id', 'none')}")
            lines.append(f"Best bio: {rl.get('best_bio_id', 'none')} (reward: {rl.get('best_reward', 0)})")
            lines.append(f"Total rotations: {rl.get('total_rotations', 0)}")
            if rl.get('should_rotate'):
                lines.append(f"ROTATION RECOMMENDED: {rl.get('rotate_reason', '')}")
        except Exception:
            pass

    # Content counts
    counts = {}
    for subdir in ["bios", "blog_posts", "interview_questions", "social_posts", "email_templates", "seo_keywords"]:
        path = os.path.join(CONTENT_DIR, subdir)
        if os.path.exists(path):
            import glob
            counts[subdir] = len(glob.glob(os.path.join(path, "*")))
    lines.append(f"\nContent inventory: {json.dumps(counts, indent=2)}")

    # Recent orchestrator events
    if os.path.exists(ORCHESTRATOR_LOG):
        try:
            with open(ORCHESTRATOR_LOG) as f:
                events = [json.loads(line) for line in f if line.strip()]
            lines.append(f"\nOrchestrator events: {len(events)}")
            for e in events[-10:]:
                lines.append(f"  {e.get('timestamp', '?')}: {e.get('component', '?')} -> {e.get('status', '?')}")
        except Exception:
            pass

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RentMasseur master orchestrator")
    parser.add_argument("--all", action="store_true", help="Run everything: stats + all rotations + content")
    parser.add_argument("--bio", action="store_true", help="Rotate bio")
    parser.add_argument("--photo", action="store_true", help="Rotate photo")
    parser.add_argument("--price", action="store_true", help="Rotate price")
    parser.add_argument("--interview", action="store_true", help="Rotate interview")
    parser.add_argument("--blog", action="store_true", help="Rotate blog")
    parser.add_argument("--stats", action="store_true", help="Collect stats only")
    parser.add_argument("--content", action="store_true", help="Generate daily content only")
    parser.add_argument("--report", action="store_true", help="Show performance report")
    parser.add_argument("--dry-run", action="store_true", help="Don't upload anything")
    args = parser.parse_args()

    os.makedirs(CONTENT_DIR, exist_ok=True)
    log_event({"component": "orchestrator", "status": "started", "args": sys.argv[1:]})

    if args.report:
        print(master_report())
        return

    if args.all:
        collect_stats()
        generate_daily_content()
        run_bio_rotation(dry_run=args.dry_run)
        run_photo_rotation(dry_run=args.dry_run)
        run_price_rotation(dry_run=args.dry_run)
        run_interview_rotation(dry_run=args.dry_run)
        run_blog_rotation(dry_run=args.dry_run)
        collect_stats()
        print(master_report())
        return

    if args.stats:
        stats = collect_stats()
        print(json.dumps(stats, indent=2))
        return

    if args.content:
        generate_daily_content()
        return

    if args.bio:
        run_bio_rotation(dry_run=args.dry_run)
    if args.photo:
        run_photo_rotation(dry_run=args.dry_run)
    if args.price:
        run_price_rotation(dry_run=args.dry_run)
    if args.interview:
        run_interview_rotation(dry_run=args.dry_run)
    if args.blog:
        run_blog_rotation(dry_run=args.dry_run)

    log_event({"component": "orchestrator", "status": "completed"})


if __name__ == "__main__":
    main()
