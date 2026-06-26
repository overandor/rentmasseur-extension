#!/usr/bin/env python3
"""Competitor scraper — scrapes top RentMasseur profiles for competitive analysis.

Fetches public profile pages and extracts: name, location, rate, bio text,
availability status, and photo count. Uses Playwright for browser-based scraping
to bypass anti-bot measures.

Usage:
    python3 competitor_scraper.py
    python3 competitor_scraper.py --urls https://rentmasseur.com/User1 https://rentmasseur.com/User2
    python3 competitor_scraper.py --output competitor_data.json
"""

import argparse
import json
import os
import sys
import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "competitor_data.json")
CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")

DEFAULT_COMPETITORS = [
    "https://rentmasseur.com/Preston_Banks",
    "https://rentmasseur.com/Tonyxxxx",
    "https://rentmasseur.com/MickeyCuteBoy",
    "https://rentmasseur.com/ExoticYoungGuy",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_with_playwright(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a page using Playwright browser automation."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(url, timeout=timeout * 1000)
            page.wait_for_load_state("networkidle", timeout=timeout * 1000)
            time.sleep(3)
            html = page.content()
            browser.close()
            return html
    except PlaywrightTimeoutError:
        logger.warning("Playwright timeout for %s", url)
        return None
    except Exception as e:
        logger.error("Playwright error for %s: %s", url, e)
        return None


def fetch_with_requests(url: str, timeout: int = 20) -> Optional[str]:
    """Fetch a page using requests with browser-like headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://rentmasseur.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("requests failed for %s: %s", url, e)
        return None


def extract_profile_data(html: str, url: str) -> dict:
    """Extract profile data from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    data = {
        "url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "name": None,
        "location": None,
        "rate": None,
        "availability": None,
        "bio_text": None,
        "photo_count": 0,
        "services": [],
        "phone": None,
    }

    # Try to extract name from h1 or title
    h1 = soup.find("h1")
    if h1:
        data["name"] = h1.get_text(strip=True)
    if not data["name"]:
        title = soup.find("title")
        if title:
            name_match = re.search(r"^(.+?)\s*[-|]", title.get_text())
            if name_match:
                data["name"] = name_match.group(1).strip()

    # Extract location
    for selector in [".location", ".profile-location", "[data-field='location']"]:
        el = soup.select_one(selector)
        if el:
            data["location"] = el.get_text(strip=True)
            break

    # Extract rate
    for selector in [".rate", ".price", "[data-field='rate']"]:
        el = soup.select_one(selector)
        if el:
            data["rate"] = el.get_text(strip=True)
            break

    # Extract bio text
    for selector in [".bio", ".about", ".description", ".profile-bio", "[data-field='bio']"]:
        el = soup.select_one(selector)
        if el:
            data["bio_text"] = el.get_text(strip=True)[:1000]
            break

    # Extract availability
    for selector in [".availability", ".status", ".badge"]:
        el = soup.select_one(selector)
        if el:
            data["availability"] = el.get_text(strip=True)
            break

    # Count photos
    photos = soup.select("img[src*='profile'], img[src*='photo'], img[class*='profile']")
    data["photo_count"] = len(photos)

    # Extract services from text
    page_text = soup.get_text().lower()
    service_keywords = [
        "deep tissue", "swedish", "hot stone", "sports massage", "trigger point",
        "aromatherapy", "reflexology", "shiatsu", "thai massage", "prenatal",
        "couples massage", "lymphatic drainage", "myofascial release", "craniosacral",
        "reiki", "chair massage", "corporate massage", "mobile massage",
    ]
    for kw in service_keywords:
        if kw in page_text:
            data["services"].append(kw)

    return data


def scrape_competitors(urls: list, output_path: str) -> list:
    """Scrape multiple competitor profiles."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    results = []

    for url in urls:
        logger.info("Scraping: %s", url)

        # Try Playwright first, fall back to requests
        html = fetch_with_playwright(url)
        if not html:
            logger.info("Playwright failed, trying requests...")
            html = fetch_with_requests(url)

        if not html:
            logger.error("Failed to fetch %s", url)
            results.append({"url": url, "error": "fetch_failed", "scraped_at": datetime.now(timezone.utc).isoformat()})
            continue

        # Check for captcha
        if "captcha" in html.lower() or "crowdsec" in html.lower():
            logger.warning("Captcha detected for %s", url)
            results.append({"url": url, "error": "captcha_blocked", "scraped_at": datetime.now(timezone.utc).isoformat()})
            continue

        data = extract_profile_data(html, url)
        results.append(data)
        logger.info("Extracted: name=%s, location=%s, rate=%s, services=%d",
                     data["name"], data["location"], data["rate"], len(data["services"]))

        time.sleep(2)

    # Save results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved %d profiles to %s", len(results), output_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="Scrape RentMasseur competitor profiles")
    parser.add_argument("--urls", nargs="*", default=DEFAULT_COMPETITORS, help="Profile URLs to scrape")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    results = scrape_competitors(args.urls, args.output)

    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    logger.info("=== Scraping complete: %d success, %d failed ===", len(successful), len(failed))

    if successful:
        avg_services = sum(len(r.get("services", [])) for r in successful) / len(successful)
        logger.info("Average services listed: %.1f", avg_services)
        logger.info("Profiles with photos: %d/%d", sum(1 for r in successful if r.get("photo_count", 0) > 0), len(successful))

    print(json.dumps({"total": len(results), "success": len(successful), "failed": len(failed)}, indent=2))


if __name__ == "__main__":
    main()
