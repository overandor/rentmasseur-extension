#!/usr/bin/env python3
"""
Mine NY non-masseur client profiles from RentMasseur.

What it does:
  1. Logs in via Playwright (or reuses saved storage state)
  2. Navigates to "Who Saw Me" page to extract visitor usernames
  3. Also hits the dashboard API for visitor data
  4. Visits each visitor's public profile to determine if they're a masseur or client
  5. Filters for NY-based visitors
  6. Saves results as JSON + screenshots

Safety:
  - Read-only — no messages, no mutations
  - Stops on CAPTCHA/blocks
  - Rate-limited between profile visits
  - Screenshots every page
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext


BASE_URL = "https://rentmasseur.com"
ARTIFACTS = Path("artifacts/ny_mining")
SCREENSHOTS = ARTIFACTS / "screenshots"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
SCREENSHOTS.mkdir(exist_ok=True)

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny",
    "staten-island-ny", "long-island-ny", "westchester-ny",
    "new-york-ny", "nyc", "newyork",
]

NY_KEYWORDS = [
    "new york", "manhattan", "brooklyn", "queens", "bronx",
    "staten island", "long island", "westchester", "nyc",
    "ny,", "ny ", ", ny", "newyork",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]', '_', s)[:60]


def detect_block(page: Page) -> Optional[str]:
    try:
        txt = page.inner_text("body")[:3000].lower()
    except Exception:
        txt = ""
    url = (page.url or "").lower()
    for needle, reason in [
        ("captcha", "captcha"), ("crowdsec", "crowdsec"),
        ("access forbidden", "forbidden"), ("verify you are human", "verification"),
        ("too many requests", "rate_limited"),
    ]:
        if needle in txt or needle in url:
            return reason
    return None


def is_ny_location(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in NY_KEYWORDS)


def screenshot(page: Page, name: str) -> str:
    path = SCREENSHOTS / f"{safe_name(name)}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        return ""
    return str(path)


def attempt_login(page: Page, context: BrowserContext, username: str, password: str) -> bool:
    try:
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        block = detect_block(page)
        if block:
            print(f"  BLOCKED: {block}")
            return False

        email_el = page.query_selector("input#email") or page.query_selector("input[name='email']")
        pass_el = page.query_selector("input#password") or page.query_selector("input[type='password']")

        if not email_el or not pass_el:
            print("  Login form not found")
            return False

        email_el.fill(username)
        pass_el.fill(password)
        time.sleep(0.5)

        login_btn = page.query_selector("button:has-text('LOGIN')") or page.query_selector("button[type='submit']")
        if login_btn and login_btn.is_visible():
            login_btn.click()
        else:
            pass_el.press("Enter")

        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)

        block = detect_block(page)
        if block:
            print(f"  Post-login block: {block}")
            return False

        if "/login" in page.url:
            print("  Login failed — still on login page")
            return False

        # Save storage state
        context.storage_state(path=str(Path(".rm_storage_state.json")))
        print(f"  Login OK — URL: {page.url}")
        return True

    except Exception as e:
        print(f"  Login error: {e}")
        return False


def scrape_who_saw_me(page: Page) -> list[dict]:
    """Navigate to Who Saw Me page and extract visitor usernames + locations."""
    visitors = []

    # Try multiple possible URLs for "Who Saw Me"
    urls_to_try = [
        f"{BASE_URL}/settings/visitors",
        f"{BASE_URL}/settings/who-saw-me",
        f"{BASE_URL}/account/visitors",
        f"{BASE_URL}/settings/stats",
    ]

    for url in urls_to_try:
        print(f"\n  Trying: {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Dismiss cookie consent
            try:
                btn = page.query_selector("button:has-text('ACCEPT ALL')")
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(1)
            except Exception:
                pass

            block = detect_block(page)
            if block:
                print(f"  Blocked: {block}")
                continue

            if "/login" in page.url or "/404" in page.url:
                print(f"  Redirected: {page.url}")
                continue

            ss = screenshot(page, f"who_saw_me_{safe_name(url.split('/')[-1])}")
            print(f"  Page loaded: {page.url}")
            print(f"  Screenshot: {ss}")

            # Try to extract visitor data from __NEXT_DATA__
            try:
                nd_text = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
                if nd_text:
                    nd = json.loads(nd_text)
                    props = nd.get("props", {}).get("pageProps", {})
                    print(f"  __NEXT_DATA__ keys: {list(props.keys())}")

                    # Look for visitors in various possible keys
                    for key in ["visitors", "whoSawMe", "whoViewed", "views", "stats", "recentVisitors", "profileViews"]:
                        if key in props:
                            data = props[key]
                            if isinstance(data, list):
                                for item in data:
                                    username = item.get("username") or item.get("user") or item.get("name") or ""
                                    location = item.get("location") or item.get("city") or item.get("state") or ""
                                    if username:
                                        visitors.append({
                                            "username": username,
                                            "location": location,
                                            "source": f"__NEXT_DATA__.{key}",
                                            "raw": {k: v for k, v in item.items() if k in [
                                                "username", "location", "city", "state", "country",
                                                "userId", "userPhoto", "ts", "timestamp", "isMasseur",
                                                "type", "role", "searchCity",
                                            ]},
                                        })
                                print(f"  Found {len(visitors)} visitors in __NEXT_DATA__.{key}")
            except Exception as e:
                print(f"  __NEXT_DATA__ parse error: {e}")

            # Also try extracting from page DOM — look for profile links
            try:
                links = page.query_selector_all("a[href]")
                seen = {v["username"] for v in visitors}
                for el in links:
                    href = el.get_attribute("href") or ""
                    text = (el.inner_text() or "").strip()
                    # Profile links are /username (single segment)
                    if href.startswith("/") and not any(x in href for x in [
                        "login", "settings", "search", "blog", "reviews", "interviews",
                        "available", "find-massage", "live-cams", "sitemap", "advertise",
                        "mailbox", "static", "_next", "images", "api", "blogs", "404",
                        "account", "gay-massage",
                    ]):
                        parts = href.strip("/").split("/")
                        if parts and parts[0] and len(parts) == 1 and parts[0] not in seen:
                            # Try to find location near this link
                            location = ""
                            try:
                                parent = el.evaluate("e => e.closest('div, li, tr, card')")
                                if parent:
                                    location = page.evaluate("(el) => el ? el.innerText : ''", parent)[:300]
                            except Exception:
                                pass

                            visitors.append({
                                "username": parts[0],
                                "location": location,
                                "source": "dom_link",
                                "raw": {"href": href, "text": text[:60]},
                            })
                            seen.add(parts[0])
                print(f"  DOM links: {len(visitors)} total visitors found")
            except Exception as e:
                print(f"  DOM extraction error: {e}")

            # Also capture the page text for analysis
            try:
                body_text = page.inner_text("body")[:5000]
                # Look for patterns like "username from location"
                # or table rows with user info
                lines = body_text.split("\n")
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 5 and len(line) < 200:
                        # Check if it looks like a visitor entry
                        if any(kw in line.lower() for kw in NY_KEYWORDS):
                            # Try to extract username from line
                            for sep in [" from ", " - ", " | ", "  "]:
                                if sep in line:
                                    parts = line.split(sep)
                                    if parts[0] and not any(x in parts[0].lower() for x in ["search", "filter", "sort", "page"]):
                                        uname = parts[0].strip()
                                        if uname and len(uname) < 40 and uname not in {v["username"] for v in visitors}:
                                            visitors.append({
                                                "username": uname,
                                                "location": line,
                                                "source": "page_text_pattern",
                                                "raw": {"line": line},
                                            })
                                    break
            except Exception:
                pass

            if visitors:
                break  # Found visitors, stop trying other URLs

        except Exception as e:
            print(f"  Error: {e}")
            continue

    return visitors


def check_profile_is_masseur(page: Page, username: str) -> dict:
    """Visit a profile and determine if it's a masseur or client."""
    result = {
        "username": username,
        "is_masseur": False,
        "location": "",
        "is_ny": False,
        "profile_text": "",
        "screenshot": "",
        "error": None,
    }

    try:
        url = f"{BASE_URL}/{username}"
        page.goto(url, wait_until="networkidle", timeout=20000)
        time.sleep(2)

        block = detect_block(page)
        if block:
            result["error"] = f"blocked:{block}"
            return result

        if "/404" in page.url or "/login" in page.url:
            result["error"] = f"redirected:{page.url}"
            return result

        result["screenshot"] = screenshot(page, f"profile_{safe_name(username)}")

        # Get page text
        body_text = page.inner_text("body")[:3000]
        result["profile_text"] = body_text[:500]

        # Check if masseur — masseur profiles have "Book Now", "Available", massage rates, etc.
        masseur_signals = ["book now", "available now", "massage", "rates", "incall", "outcall",
                          "modalities", "session", "booking", "schedule"]
        masseur_score = sum(1 for s in masseur_signals if s in body_text.lower())
        result["is_masseur"] = masseur_score >= 3

        # Extract location
        try:
            nd_text = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
            if nd_text:
                nd = json.loads(nd_text)
                props = nd.get("props", {}).get("pageProps", {})
                user = props.get("user", props.get("masseur", props.get("profile", {})))
                if isinstance(user, dict):
                    location = user.get("location") or user.get("city") or ""
                    state = user.get("state") or ""
                    country = user.get("country") or ""
                    search_city = user.get("searchCity") or ""
                    result["location"] = f"{location}, {state} {country}".strip(", ")
                    result["is_ny"] = is_ny_location(result["location"]) or is_ny_location(search_city)
                    # Check isMasseur flag if present
                    if "isMasseur" in user:
                        result["is_masseur"] = bool(user["isMasseur"])
                    elif "role" in user:
                        result["is_masseur"] = user.get("role") == "masseur"
        except Exception:
            pass

        # Fallback: check location from page text
        if not result["location"]:
            for line in body_text.split("\n"):
                if any(kw in line.lower() for kw in NY_KEYWORDS):
                    result["location"] = line.strip()[:100]
                    result["is_ny"] = True
                    break

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    username = os.getenv("RM_USER") or os.getenv("RENTMASSEUR_USER") or ""
    password = os.getenv("RM_PASS") or os.getenv("RENTMASSEUR_PASS") or ""

    if not username or not password:
        print("!! Set RM_USER and RM_PASS env vars")
        return

    print(f"\n=== RM NY Client Profile Mining ===")
    print(f"  Account: {username}")
    print(f"  Target: NY non-masseur client profiles")

    all_visitors = []
    ny_clients = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        storage_state = Path(".rm_storage_state.json")
        ctx_kwargs = {
            "viewport": {"width": 1440, "height": 1200},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        # Try to reuse saved session
        if storage_state.exists():
            ctx_kwargs["storage_state"] = str(storage_state)
            print("  Using saved storage state")

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        # Check if session is still valid
        page.goto(f"{BASE_URL}/settings", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        if "/login" in page.url:
            print("  Session expired — re-logging in")
            logged_in = attempt_login(page, context, username, password)
            if not logged_in:
                print("!! Login failed — aborting")
                browser.close()
                return
        else:
            print("  Session valid — already logged in")

        # Step 1: Scrape "Who Saw Me" visitors
        print(f"\n--- Step 1: Scraping Who Saw Me ---")
        visitors = scrape_who_saw_me(page)
        all_visitors.extend(visitors)
        print(f"\n  Total visitors found: {len(visitors)}")

        # Step 2: Also check dashboard API for visitor data
        print(f"\n--- Step 2: Checking dashboard API ---")
        try:
            # Intercept API responses
            api_responses = []

            def on_response(response):
                url = response.url
                if "rentmasseur.com/api" in url:
                    try:
                        body = response.text()
                        api_responses.append({
                            "url": url.replace(BASE_URL, ""),
                            "status": response.status,
                            "body_preview": body[:1000],
                            "body_len": len(body),
                        })
                    except Exception:
                        pass

            page.on("response", on_response)

            page.goto(f"{BASE_URL}/settings", wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Save API responses
            api_path = ARTIFACTS / "dashboard_api_responses.json"
            api_path.write_text(json.dumps(api_responses, indent=2, default=str), encoding="utf-8")
            print(f"  Captured {len(api_responses)} API responses → {api_path}")

            # Check __NEXT_DATA__ on dashboard for visitor info
            try:
                nd_text = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
                if nd_text:
                    nd = json.loads(nd_text)
                    props = nd.get("props", {}).get("pageProps", {})
                    nd_path = ARTIFACTS / "dashboard_next_data.json"
                    # Save full next data for analysis
                    nd_path.write_text(json.dumps(props, indent=2, default=str)[:50000], encoding="utf-8")
                    print(f"  Dashboard __NEXT_DATA__ keys: {list(props.keys())}")
                    print(f"  Saved to: {nd_path}")

                    # Look for visitor-related data
                    for key in props:
                        val = props[key]
                        if isinstance(val, dict):
                            for subkey in ["visitors", "whoSawMe", "whoViewed", "views", "recentVisitors", "profileViews"]:
                                if subkey in val:
                                    print(f"  Found {key}.{subkey}!")
                                    data = val[subkey]
                                    if isinstance(data, list):
                                        for item in data:
                                            uname = item.get("username") or item.get("user") or ""
                                            if uname and uname not in {v["username"] for v in all_visitors}:
                                                all_visitors.append({
                                                    "username": uname,
                                                    "location": item.get("location", ""),
                                                    "source": f"dashboard.{key}.{subkey}",
                                                    "raw": item,
                                                })
            except Exception as e:
                print(f"  Dashboard __NEXT_DATA__ error: {e}")

        except Exception as e:
            print(f"  Dashboard API error: {e}")

        # Step 3: Visit each visitor profile to check if masseur or client + NY
        print(f"\n--- Step 3: Checking {len(all_visitors)} visitor profiles ---")
        checked = []
        for i, visitor in enumerate(all_visitors):
            uname = visitor["username"]
            print(f"\n  [{i+1}/{len(all_visitors)}] Checking: {uname}")

            profile_info = check_profile_is_masseur(page, uname)
            profile_info["source"] = visitor.get("source", "")
            checked.append(profile_info)

            if profile_info["is_masseur"]:
                print(f"    → MASSEUR (skipping)")
            else:
                print(f"    → CLIENT")
                if profile_info["is_ny"]:
                    print(f"    → NY CLIENT ✓")
                    ny_clients.append(profile_info)
                else:
                    print(f"    → Location: {profile_info['location']}")

            if profile_info.get("error"):
                print(f"    → Error: {profile_info['error']}")

            # Rate limit
            time.sleep(2)

        browser.close()

    # Step 4: Save results
    print(f"\n=== Results ===")
    print(f"  Total visitors found: {len(all_visitors)}")
    print(f"  Profiles checked: {len(checked)}")
    print(f"  Masseurs: {sum(1 for c in checked if c['is_masseur'])}")
    print(f"  Clients: {sum(1 for c in checked if not c['is_masseur'])}")
    print(f"  NY clients: {len(ny_clients)}")

    # Save all results
    results = {
        "timestamp": now_iso(),
        "account": username,
        "summary": {
            "total_visitors": len(all_visitors),
            "profiles_checked": len(checked),
            "masseurs": sum(1 for c in checked if c["is_masseur"]),
            "clients": sum(1 for c in checked if not c["is_masseur"]),
            "ny_clients": len(ny_clients),
        },
        "all_visitors": all_visitors,
        "checked_profiles": checked,
        "ny_clients": ny_clients,
    }

    results_path = ARTIFACTS / "ny_client_mining_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n  Results: {results_path}")
    print(f"  Screenshots: {SCREENSHOTS}/")

    # Print NY clients
    if ny_clients:
        print(f"\n--- NY Client Profiles ---")
        for c in ny_clients:
            print(f"  {c['username']:25s} | {c['location'][:50]}")
    else:
        print(f"\n  No NY clients found — may need to check more visitors or different pages")


if __name__ == "__main__":
    main()
