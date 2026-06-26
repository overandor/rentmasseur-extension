#!/usr/bin/env python3
"""GA + RL LLM optimizer for RentMasseur revenue maximization.

Goal: generate $300/day through optimized bios, prices, photos, and CTAs.

Combines:
- Genetic Algorithm: population of account configurations, selection, crossover, mutation
- Reinforcement Learning: reward = revenue estimate from clicks/calls/bookings
- LLM: generates mutations and new variants
- Live Selenium: applies winning configurations to RentMasseur profile

Revenue model:
  revenue = (views * view_to_click_rate * avg_click_value) +
            (phone_clicks * call_conversion_rate * avg_session_price) +
            (booking_inquiries * avg_session_price)

Default: 5% click rate, 20% call conversion, $200 avg session, $300/day target.

Usage:
    python3 ga_rl_optimizer.py
    python3 ga_rl_optimizer.py --population 20 --generations 10 --target 300
    python3 ga_rl_optimizer.py --apply-winner  # apply best config to profile
    python3 ga_rl_optimizer.py --report
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
REBRANDLY_LINK = os.getenv("REBRANDLY_LINK", "https://rebrand.ly/your-booking-link")

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
GA_STATE_PATH = os.path.join(CONTENT_DIR, "ga_rl_state.json")

# Revenue constants
AVG_SESSION_PRICE = 200
CALL_CONVERSION_RATE = 0.20
VIEW_TO_CLICK_RATE = 0.05
BOOKING_CLOSE_RATE = 0.40
REVENUE_TARGET = 300

REWARD_WEIGHTS = {
    "views": 1,
    "email_clicks": 5,
    "phone_clicks": 10,
    "booking_inquiries": 50,
    "favorites": 3,
    "messages": 8,
}


def _groq_chat(system_prompt: str, user_prompt: str, max_tokens: int = 800, retries: int = 3) -> Optional[str]:
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
        except Exception as e:
            logger.error("Groq API error: %s", e)
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    return None


class AccountConfig:
    """One individual in the GA population — a complete account configuration."""

    def __init__(self, bio=None, price=None, photo_style=None, cta=None, headline=None):
        self.bio = bio or ""
        self.price = price or 200
        self.photo_style = photo_style or "professional"
        self.cta = cta or "Call me now to book your session"
        self.headline = headline or "Elite Male Masseur in Manhattan"
        self.fitness = 0
        self.revenue_estimate = 0
        self.reward = 0
        self.id = f"cfg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        self.generation = 0
        self.uses = 0

    def to_dict(self):
        return {
            "id": self.id,
            "bio": self.bio[:200],
            "price": self.price,
            "photo_style": self.photo_style,
            "cta": self.cta,
            "headline": self.headline,
            "fitness": self.fitness,
            "revenue_estimate": self.revenue_estimate,
            "reward": self.reward,
            "generation": self.generation,
            "uses": self.uses,
        }

    @classmethod
    def from_dict(cls, d):
        c = cls(
            bio=d.get("bio", ""),
            price=d.get("price", 200),
            photo_style=d.get("photo_style", "professional"),
            cta=d.get("cta", "Call me now to book your session"),
            headline=d.get("headline", "Elite Male Masseur in Manhattan"),
        )
        c.id = d.get("id", c.id)
        c.fitness = d.get("fitness", 0)
        c.revenue_estimate = d.get("revenue_estimate", 0)
        c.reward = d.get("reward", 0)
        c.generation = d.get("generation", 0)
        c.uses = d.get("uses", 0)
        return c


def generate_random_bio() -> str:
    system_prompt = (
        "You are a hilarious, magnetic copywriter for RentMasseur. "
        "Write a bio under 200 words that makes clients laugh and immediately CALL. "
        "Include urgency, SEO keywords (massage, Manhattan, therapeutic), and a strong CTA. "
        "The bio must be funny and conversion-focused. "
        f"Include this clickable booking link: {REBRANDLY_LINK}. "
        "No explicit content. Write ONLY the bio text."
    )
    user_prompt = (
        "Write a funny, phone-call-driving bio for a male masseur in Manhattan. "
        "Make it better than any competitor bio on RentMasseur."
    )
    return _groq_chat(system_prompt, user_prompt, max_tokens=600) or ""


def generate_mutated_bio(parent_bio: str) -> str:
    system_prompt = (
        "You are a bio optimization expert. Take the given bio and mutate it to "
        "generate MORE phone calls and more revenue. Keep what works, change what doesn't. "
        "Make it funnier, more urgent, more clickable. Include a strong CTA. "
        f"Must include this clickable booking link: {REBRANDLY_LINK}. "
        "Return ONLY the bio text."
    )
    user_prompt = f"Mutate this bio to maximize phone calls:\n\n{parent_bio}\n\nMake it funnier and more compelling."
    return _groq_chat(system_prompt, user_prompt, max_tokens=600) or parent_bio


def generate_headline() -> str:
    options = [
        "Elite Male Masseur in Manhattan",
        "Your Private Massage Therapist in NYC",
        "Deep Tissue & Sensory Massage by Request",
        "Manhattan's Most Sought-After Masseur",
        "Therapeutic Touch in the Heart of NYC",
        "Late-Night Relief Available Now",
        "Premium In-Home Massage Experience",
        "The Masseur Who Actually Listens",
    ]
    return random.choice(options)


def generate_cta() -> str:
    options = [
        "Call me now to book your session",
        "Pick up the phone and call today",
        "Text or call — I'm available now",
        "Don't wait — call me right now",
        "Book now: your body will thank you",
        "Call today for same-day availability",
    ]
    return random.choice(options)


def calculate_revenue_estimate(stats: dict) -> float:
    """Estimate daily revenue from engagement stats."""
    views = stats.get("views", 0)
    phone_clicks = stats.get("phone_clicks", 0)
    email_clicks = stats.get("email_clicks", 0)
    booking_inquiries = stats.get("booking_inquiries", 0)
    messages = stats.get("messages", 0)

    view_revenue = views * VIEW_TO_CLICK_RATE * AVG_SESSION_PRICE
    call_revenue = phone_clicks * CALL_CONVERSION_RATE * AVG_SESSION_PRICE
    inquiry_revenue = booking_inquiries * BOOKING_CLOSE_RATE * AVG_SESSION_PRICE
    message_revenue = messages * 0.10 * AVG_SESSION_PRICE
    email_revenue = email_clicks * 0.05 * AVG_SESSION_PRICE

    return round(view_revenue + call_revenue + inquiry_revenue + message_revenue + email_revenue, 2)


def calculate_fitness(stats: dict, revenue_target: float = REVENUE_TARGET) -> float:
    """Fitness score: how close to revenue target + reward quality."""
    revenue = calculate_revenue_estimate(stats)
    reward = 0
    for key, weight in REWARD_WEIGHTS.items():
        reward += stats.get(key, 0) * weight

    # Revenue proximity bonus
    target_bonus = max(0, min(100, (revenue / revenue_target) * 100))

    # Penalty for being far from target
    target_penalty = abs(revenue_target - revenue) * 0.1

    fitness = reward + target_bonus - target_penalty
    return round(fitness, 2)


def load_ga_state() -> dict:
    if os.path.exists(GA_STATE_PATH):
        try:
            with open(GA_STATE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "population": [],
        "generation": 0,
        "best_config": None,
        "best_fitness": 0,
        "best_revenue": 0,
        "history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_ga_state(state: dict):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    with open(GA_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_latest_stats() -> dict:
    """Get latest stats from rl_feedback.py state."""
    rl_path = os.path.join(CONTENT_DIR, "rl_state.json")
    if os.path.exists(rl_path):
        try:
            with open(rl_path, "r") as f:
                rl = json.load(f)
            current = rl.get("current_bio_id")
            if current and current in rl.get("bios", {}):
                bio_entry = rl["bios"][current]
                return bio_entry.get("last_stats", {})
        except Exception:
            pass
    return {"views": 0, "phone_clicks": 0, "email_clicks": 0, "booking_inquiries": 0, "messages": 0, "favorites": 0}


def create_initial_population(size: int) -> list:
    """Create initial GA population."""
    logger.info("Creating initial population of %d", size)
    population = []
    for i in range(size):
        bio = generate_random_bio()
        config = AccountConfig(
            bio=bio,
            price=random.choice([120, 150, 180, 200, 220, 250, 280, 300]),
            photo_style=random.choice(["professional", "casual", "athletic", "luxury", "mystery"]),
            cta=generate_cta(),
            headline=generate_headline(),
        )
        config.generation = 0
        population.append(config)
        logger.info("Individual %d: %d chars, price $%d", i, len(bio), config.price)
        time.sleep(1)
    return population


def evaluate_population(population: list, stats: dict) -> list:
    """Evaluate fitness for each individual using current stats."""
    for config in population:
        # Adjust stats based on config price sensitivity
        # Higher price = lower conversion, lower price = higher conversion
        price_factor = 1.0 - ((config.price - 200) / 1000.0)
        adjusted_stats = stats.copy()
        adjusted_stats["phone_clicks"] = int(adjusted_stats.get("phone_clicks", 0) * price_factor)
        adjusted_stats["booking_inquiries"] = int(adjusted_stats.get("booking_inquiries", 0) * price_factor)

        config.revenue_estimate = calculate_revenue_estimate(adjusted_stats)
        config.fitness = calculate_fitness(adjusted_stats)
        config.reward = sum(adjusted_stats.get(k, 0) * v for k, v in REWARD_WEIGHTS.items())

    return sorted(population, key=lambda x: x.fitness, reverse=True)


def select_parents(population: list, num_parents: int) -> list:
    """Tournament selection."""
    selected = []
    for _ in range(num_parents):
        tournament = random.sample(population, min(3, len(population)))
        winner = max(tournament, key=lambda x: x.fitness)
        selected.append(winner)
    return selected


def crossover(parent1: AccountConfig, parent2: AccountConfig) -> AccountConfig:
    """Combine two parents into one child."""
    child = AccountConfig()
    child.bio = parent1.bio if random.random() > 0.5 else parent2.bio
    child.price = parent1.price if random.random() > 0.5 else parent2.price
    child.photo_style = parent1.photo_style if random.random() > 0.5 else parent2.photo_style
    child.cta = parent1.cta if random.random() > 0.5 else parent2.cta
    child.headline = parent1.headline if random.random() > 0.5 else parent2.headline
    child.generation = max(parent1.generation, parent2.generation) + 1
    return child


def mutate(config: AccountConfig, generation: int) -> AccountConfig:
    """Mutate an individual using LLM and random perturbations."""
    # Mutate bio with LLM
    if random.random() < 0.7:
        config.bio = generate_mutated_bio(config.bio) or config.bio

    # Mutate price
    if random.random() < 0.5:
        delta = random.choice([-30, -20, -10, 10, 20, 30, 50])
        config.price = max(80, min(500, config.price + delta))

    # Mutate CTA
    if random.random() < 0.3:
        config.cta = generate_cta()

    # Mutate headline
    if random.random() < 0.3:
        config.headline = generate_headline()

    # Mutate photo style
    if random.random() < 0.3:
        config.photo_style = random.choice(["professional", "casual", "athletic", "luxury", "mystery", "warm"])

    config.generation = generation
    return config


def evolve(population_size: int = 12, generations: int = 5, target: float = 300) -> AccountConfig:
    """Run genetic algorithm to evolve best account config."""
    state = load_ga_state()

    if state.get("population"):
        population = [AccountConfig.from_dict(d) for d in state["population"]]
    else:
        population = create_initial_population(population_size)

    current_gen = state.get("generation", 0)
    stats = get_latest_stats()
    best_overall = state.get("best_config")
    best_fitness = state.get("best_fitness", 0)

    for gen in range(current_gen + 1, current_gen + generations + 1):
        logger.info("=== Generation %d ===", gen)
        population = evaluate_population(population, stats)

        logger.info("Best fitness: %.2f, Best revenue: $%.2f", population[0].fitness, population[0].revenue_estimate)

        if population[0].fitness > best_fitness:
            best_fitness = population[0].fitness
            best_overall = population[0].to_dict()
            logger.info("New best config found!")

        # Selection
        parents = select_parents(population, max(2, population_size // 3))

        # Crossover + mutation
        new_population = []
        new_population.append(population[0])  # Elitism
        new_population.append(population[1])  # Keep second best

        while len(new_population) < population_size:
            p1, p2 = random.sample(parents, 2)
            child = crossover(p1, p2)
            child = mutate(child, gen)
            new_population.append(child)

        population = new_population

        # Save state
        state["population"] = [p.to_dict() for p in population]
        state["generation"] = gen
        state["best_config"] = best_overall
        state["best_fitness"] = best_fitness
        state["best_revenue"] = population[0].revenue_estimate
        state["history"].append({
            "generation": gen,
            "best_fitness": population[0].fitness,
            "best_revenue": population[0].revenue_estimate,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        save_ga_state(state)

        time.sleep(1)

    return population[0]


def apply_config_to_profile(config: AccountConfig) -> bool:
    """Apply the winning GA config to the live RentMasseur profile."""
    try:
        from rentmasseur_core import setup_driver, login, update_bio, save_bio_field

        driver = setup_driver(headless=True)
        try:
            if not login(driver):
                logger.error("Login failed")
                return False

            logger.info("Applying winning GA config to profile...")
            logger.info("Price: $%d, CTA: %s, Headline: %s", config.price, config.cta, config.headline)

            # Combine bio + CTA + rebrandly link
            full_bio = f"{config.headline}\n\n{config.bio}\n\n{config.cta}\nBook now: {REBRANDLY_LINK}"

            result = update_bio(driver, "")
            if result is None or (isinstance(result, dict) and result.get("error")):
                logger.error("Could not find bio field")
                return False

            field_info, current_bio = result
            saved = save_bio_field(driver, field_info, full_bio)
            if not saved:
                logger.error("Failed to save bio")
                return False

            logger.info("Winning config applied successfully")
            return True
        finally:
            driver.quit()
    except Exception as e:
        logger.error("Apply config error: %s", e)
        return False


def report():
    state = load_ga_state()
    print("=" * 60)
    print("GA + RL REVENUE OPTIMIZER REPORT")
    print("=" * 60)
    print(f"Generation: {state.get('generation', 0)}")
    print(f"Best fitness: {state.get('best_fitness', 0)}")
    print(f"Best revenue estimate: ${state.get('best_revenue', 0)}")
    print(f"Revenue target: ${REVENUE_TARGET}")

    best = state.get("best_config")
    if best:
        print(f"\nBest config:")
        print(f"  ID: {best.get('id')}")
        print(f"  Price: ${best.get('price')}")
        print(f"  CTA: {best.get('cta')}")
        print(f"  Headline: {best.get('headline')}")
        print(f"  Photo style: {best.get('photo_style')}")
        print(f"  Bio: {best.get('bio', '')[:200]}...")

    print(f"\nHistory: {len(state.get('history', []))} generations")
    for h in state.get("history", [])[-5:]:
        print(f"  Gen {h.get('generation')}: fitness={h.get('best_fitness')}, revenue=${h.get('best_revenue')}")


def main():
    parser = argparse.ArgumentParser(description="GA + RL optimizer for RentMasseur revenue")
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--target", type=float, default=REVENUE_TARGET)
    parser.add_argument("--apply-winner", action="store_true", help="Apply best config to live profile")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.report:
        report()
        return

    if args.apply_winner:
        state = load_ga_state()
        best = state.get("best_config")
        if not best:
            logger.error("No winning config found. Run evolution first.")
            sys.exit(1)
        config = AccountConfig.from_dict(best)
        if args.dry_run:
            print(f"Would apply config: {config.to_dict()}")
            return
        success = apply_config_to_profile(config)
        sys.exit(0 if success else 1)

    # Run evolution
    winner = evolve(population_size=args.population, generations=args.generations, target=args.target)
    logger.info("=" * 60)
    logger.info("EVOLUTION COMPLETE")
    logger.info("Winner: %s", winner.id)
    logger.info("Revenue estimate: $%.2f (target: $%.2f)", winner.revenue_estimate, args.target)
    logger.info("Fitness: %.2f", winner.fitness)
    logger.info("=" * 60)

    if args.dry_run:
        print(f"\nDry run — not applying. Winner:\n{json.dumps(winner.to_dict(), indent=2)}")
        return

    # Apply winner if it's close to target or better than current
    if winner.revenue_estimate >= args.target * 0.5:
        logger.info("Applying winner to live profile...")
        success = apply_config_to_profile(winner)
        print(json.dumps({
            "winner": winner.to_dict(),
            "applied": success,
            "revenue_estimate": winner.revenue_estimate,
            "target": args.target,
            "gap": round(args.target - winner.revenue_estimate, 2),
        }, indent=2))
        sys.exit(0 if success else 1)
    else:
        logger.warning("Winner revenue $%.2f too far from target $%.2f — not applying", winner.revenue_estimate, args.target)
        print(json.dumps({
            "winner": winner.to_dict(),
            "applied": False,
            "reason": "revenue_too_low",
            "revenue_estimate": winner.revenue_estimate,
            "target": args.target,
        }, indent=2))


if __name__ == "__main__":
    main()
