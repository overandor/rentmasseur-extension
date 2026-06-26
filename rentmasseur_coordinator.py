#!/usr/bin/env python3
"""
RentMasseur Coordinator — uses intent router to pick top strategies,
generates bios, auto-saves to files, and updates the best one to the site.
"""

import os
import sys
import json
import logging
import time
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Strategy definitions
STRATEGIES = {
    "sensory_luxury": "Write a luxurious, sensory-rich bio. Vivid imagery: warm oils, candlelight, silk, aromatherapy. Premium experience, discretion, bespoke sessions. Sophisticated, intimate, high-end. CTA.",
    "therapeutic_expert": "Professional, therapeutic bio. Certifications, deep tissue, Swedish, sports, trigger point. Pain relief, recovery, wellness. Clinical yet warm, authoritative. CTA.",
    "mystery_desire": "Magnetic, mysterious bio. Tease the experience. Confident, alluring. Curiosity and urgency. Enigmatic, seductive-but-classy. Strong CTA.",
    "local_hustle": "Grounded, local-vibe for Manhattan NYC. Neighborhood energy, convenience, go-to masseur. Friendly, approachable, confident. CTA for easy booking.",
    "transformation_story": "Mini-story bio. Client problem (stress, tension, exhaustion) leads to your massage as solution. Empathetic, inspiring, results-oriented. Emotional hook + CTA.",
    "night_owl": "Late-night availability angle. Available when others aren't. Private evening sessions for busy professionals. Intimate, exclusive, after-hours. CTA.",
    "athlete_recovery": "Target gym-goers and athletes. Pre/post-workout massage, muscle recovery, injury prevention. Performance-focused, energetic, results-driven. CTA.",
    "ceo_executive": "Executive wellness bio. High-stress relief for CEOs, founders, professionals. Time-efficient, powerful, transformative. Discreet, premium. CTA.",
    "spiritual_healer": "Holistic, spiritual approach. Energy work, chakras, mindfulness, breathwork. Calming, nurturing, soulful. CTA for inner peace.",
    "traveler_companion": "Bio for out-of-town visitors. Jet lag relief, welcome to NYC, concierge-style service. Friendly, worldly, accommodating. CTA.",
    "medical_referral": "Clinical, doctor-recommended angle. Back pain, sciatica, posture correction. Evidence-based, professional, reassuring. CTA.",
    "artist_soul": "Creative, artistic bio. Massage as art form, body as canvas, intuitive touch. Poetic, expressive, unique. CTA.",
    "discrete_confidential": "Absolute discretion angle. Private studio, no waiting room, confidential, judgment-free. Safe, secure, trusted. CTA for VIP clients.",
    "first_timer": "Welcoming first-timers. No experience needed, guided session, gentle introduction. Warm, patient, educational. CTA.",
    "seasonal_special": "Seasonal theme. Winter warmth, summer cool-down, holiday stress relief. Timely, festive, relevant. CTA.",
    "couples_duo": "Couples massage angle. Partners, friends, duet sessions. Romantic, bonding, shared experience. CTA.",
    "bodybuilder_therapy": "Heavy lifting recovery. Deep pressure, muscle breakdown, fascia release. Intense, powerful, respected. CTA.",
    "yoga_fusion": "Yoga + massage fusion. Stretching, flexibility, mind-body connection. Flow, balance, zen. CTA.",
    "luxury_concierge": "White-glove service. In-home, hotel, personal concierge. Elite, effortless, bespoke. CTA for VIP booking.",
    "recovery_addiction": "Sober wellness angle. Clean living, recovery support, healthy coping. Supportive, non-judgmental, empowering. CTA.",
    "military_veteran": "Veteran-friendly, service-member respect. Camaraderie, PT recovery, brotherhood. Honorable, strong, understanding. CTA.",
    "lgbtq_pride": "Pride-forward, inclusive bio. Safe space, community, authentic self-expression. Celebratory, welcoming, proud. CTA.",
    "senior_gentle": "Senior-friendly, gentle touch. Mobility, arthritis, circulation. Patient, respectful, nurturing. CTA.",
    "office_relief": "Desk job recovery. Neck pain, carpal tunnel, posture. Corporate warrior relief. Practical, relatable, urgent. CTA.",
    "dancer_flexibility": "Dancer and performer focused. Flexibility, maintenance, injury prevention. Graceful, dedicated, artistic. CTA.",
    "meditation_guide": "Guided meditation + massage. Mindfulness, breath, presence. Tranquil, centered, deep. CTA.",
    "hot_stone_specialist": "Hot stone specialty. Warm stones, heat therapy, deep relaxation. Expert, unique, indulgent. CTA.",
    "quick_lunch": "Express lunch-break massage. 30-45 min, in-and-out, midday recharge. Fast, effective, convenient. CTA.",
    "birthday_gift": "Gift-worthy experience. Treat yourself, special occasion, deserved indulgence. Celebratory, gift-like, memorable. CTA.",
    "weekly_ritual": "Subscription/recurring angle. Weekly maintenance, body upkeep, ritual. Committed, long-term, investment in self. CTA for repeat booking.",
}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", default="true")
    parser.add_argument("--skip-availability", action="store_true")
    parser.add_argument("--skip-bio", action="store_true")
    parser.add_argument("--pick-best", action="store_true", help="Use intent router to pick top strategies")
    parser.add_argument("--top-n", type=int, default=5, help="Number of strategies to run when using intent router")
    args = parser.parse_args()

    from rentmasseur_core import (
        setup_driver, login, set_availability_24_7,
        update_bio, groq_generate_bio, save_bio_field,
    )
    from intent_router import route_intents

    results = {"availability": False, "bio": False, "login": False, "strategies_run": 0, "top_strategies": []}
    driver = setup_driver(headless=args.headless.lower() != "false")

    try:
        if not login(driver):
            print(json.dumps({"login": False, "bio": False, "availability": False}))
            sys.exit(1)
        results["login"] = True

        if not args.skip_availability:
            results["availability"] = set_availability_24_7(driver)

        if not args.skip_bio:
            # Get current bio field info
            bio_res = update_bio(driver, "")
            if bio_res is None or (isinstance(bio_res, dict) and bio_res.get("error")):
                logger.error("Could not find bio field")
                results["bio"] = False
            else:
                field_info, current_bio = bio_res

                if args.pick_best:
                    # Use intent router to pick top strategies
                    top_strategies = route_intents(args.top_n)
                    results["top_strategies"] = top_strategies
                    logger.info("Intent router selected: %s", top_strategies)
                else:
                    # Run all strategies
                    top_strategies = list(STRATEGIES.keys())

                generated = []
                for strategy_name in top_strategies:
                    prompt = STRATEGIES.get(strategy_name)
                    if not prompt:
                        continue
                    bio = groq_generate_bio(strategy_name, prompt, current_bio)
                    if bio:
                        generated.append({"strategy": strategy_name, "bio": bio, "chars": len(bio)})
                    time.sleep(1)  # rate limit buffer

                results["strategies_run"] = len(generated)
                logger.info("Generated %d bios", len(generated))

                if generated:
                    # Pick longest bio as best
                    best = max(generated, key=lambda x: x["chars"])
                    logger.info("Best bio: strategy=%s chars=%d", best["strategy"], best["chars"])
                    saved = save_bio_field(driver, field_info, best["bio"])
                    results["bio"] = saved
                    results["best_strategy"] = best["strategy"]
                else:
                    results["bio"] = False

    finally:
        driver.quit()

    print(json.dumps(results, indent=2))
    ok = results["login"] and (args.skip_availability or results["availability"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
