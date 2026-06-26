#!/usr/bin/env python3
"""RentMasseur availability checker.

This script fetches provider profile pages and records whether each provider
appears to be available. It is designed to run in CI/CD on a schedule.

Usage:
    python3 checker.py                    # live scrape
    python3 checker.py --mock           # demo with synthetic data
    python3 checker.py --output data/availability.json
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    PlaywrightTimeoutError = TimeoutError

DEFAULT_PROVIDERS = "providers.json"
DEFAULT_OUTPUT = "availability.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def load_providers(path):
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, dict) and "providers" in data:
        return data["providers"]
    return data


def fetch_profile(url, timeout=20):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://rentmasseur.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    time.sleep(random.uniform(1.5, 3.5))
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_availability(html):
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    body_lower = text.lower()
    is_available = bool(
        re.search(r"available now|available today|open now", body_lower)
    )

    rate_match = re.search(r"\$\d+(?:/hr| per hour|\.\d{2})", text)
    rate = rate_match.group(0) if rate_match else ""

    location_match = re.search(
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:NY|NJ|CA|TX|FL|IL|PA|OH|GA|NC|MI))",
        text,
    )
    location = location_match.group(1) if location_match else ""

    name = ""
    title_match = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
    if title_match:
        title = title_match.group(1).strip()
        name_match = re.match(r"^(.+?)\s*[-|]", title)
        name = name_match.group(1).strip() if name_match else title

    status = "available" if is_available else "unknown"
    return {
        "name": name,
        "status": status,
        "rate": rate,
        "location": location,
        "sample_text": text[:200],
    }


def check_provider(provider, mock=False):
    url = provider.get("url")
    slug = provider.get("slug") or url.rstrip("/").split("/")[-1]
    if not url:
        raise ValueError(f"Provider missing URL: {provider}")

    if mock:
        return {
            "slug": slug,
            "url": url,
            "name": provider.get("name", "Mock Provider"),
            "status": provider.get("mock_status", "available"),
            "rate": provider.get("rate", "$150/hr"),
            "location": provider.get("location", "New York, NY"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": "mock",
        }

    html = fetch_profile(url)
    result = extract_availability(html)
    result["slug"] = slug
    result["url"] = url
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    result["mode"] = "live"
    return result


def run_check(providers_path, output_path, mock=False):
    providers = load_providers(providers_path)
    results = []
    errors = []
    for provider in providers:
        try:
            result = check_provider(provider, mock=mock)
            results.append(result)
        except Exception as e:
            errors.append({"provider": provider, "error": str(e)})

    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock" if mock else "live",
        "count": len(results),
        "providers": results,
        "errors": errors,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(record, f, indent=2)

    return record


def main():
    parser = argparse.ArgumentParser(description="Check RentMasseur availability")
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--mock", action="store_true", help="Use synthetic data")
    args = parser.parse_args()

    record = run_check(args.providers, args.output, mock=args.mock)
    print(json.dumps(record, indent=2))
    if record["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
