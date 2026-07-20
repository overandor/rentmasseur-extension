#!/usr/bin/env python3
"""
RM API + XPath Playwright Probe — discovers real endpoints and selectors.

What it does:
  1. Opens RM with Playwright (headed, persistent profile)
  2. Intercepts all fetch/XHR API calls → logs method, URL, status, body
  3. Navigates key pages (login, dashboard, availability, about/bio, search, mailbox)
  4. Discovers XPath selectors for visible form fields and buttons
  5. Screenshots every page
  6. Writes JSON receipt with all findings

Usage:
  python3 rm_ci/playwright_probe.py --headed
  python3 rm_ci/playwright_probe.py --headed --login  # attempt login with .env creds
  python3 rm_ci/playwright_probe.py --headed --page about  # probe single page
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext


BASE_URL = "https://rentmasseur.com"
ARTIFACTS = Path("artifacts/probe")
ARTIFACTS.mkdir(parents=True, exist_ok=True)
(ARTIFACTS / "screenshots").mkdir(exist_ok=True)
(ARTIFACTS / "api_calls").mkdir(exist_ok=True)


PAGES = {
    "login": {"url": f"{BASE_URL}/login", "needs_login": False},
    "dashboard": {"url": f"{BASE_URL}/settings", "needs_login": True},
    "availability": {"url": f"{BASE_URL}/settings?availability=1", "needs_login": True},
    "about": {"url": f"{BASE_URL}/settings/about", "needs_login": True},
    "search": {"url": f"{BASE_URL}/search/manhattan-ny", "needs_login": False},
    "mailbox": {"url": f"{BASE_URL}/mailbox", "needs_login": True},
    "compose": {"url": f"{BASE_URL}/mailbox/compose", "needs_login": True},
    "profile": {"url": f"{BASE_URL}/karpathianwolf", "needs_login": False},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]', '_', s)[:60]


class APIInterceptor:
    """Captures all API calls during page navigation."""

    def __init__(self):
        self.calls: list[dict] = []

    def on_request(self, request):
        url = request.url
        # Only capture RM API calls, not third-party
        if "rentmasseur.com/api" in url or "/api/" in url:
            self.calls.append({
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
                "post_data": request.post_data,
                "ts": now_iso(),
            })

    def on_response(self, response):
        url = response.url
        if "rentmasseur.com/api" in url or "/api/" in url:
            # Update last matching call with response info
            for call in reversed(self.calls):
                if call["url"] == url and "status" not in call:
                    call["status"] = response.status
                    call["status_text"] = response.status_text
                    try:
                        body = response.text()
                        call["response_body"] = body[:2000]
                        call["response_body_len"] = len(body)
                    except Exception:
                        call["response_body"] = None
                    break

    def save(self, page_name: str):
        path = ARTIFACTS / "api_calls" / f"{safe_name(page_name)}_api.json"
        path.write_text(json.dumps(self.calls, indent=2, default=str), encoding="utf-8")
        return path


def discover_xpaths(page: Page) -> dict:
    """Discover XPath selectors for visible form fields and buttons."""
    findings = {
        "inputs": [],
        "textareas": [],
        "buttons": [],
        "links_profile": [],
        "selects": [],
        "contenteditable": [],
    }

    # Inputs
    for el in page.query_selector_all("input"):
        try:
            if not el.is_visible():
                continue
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            itype = el.get_attribute("type") or ""
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            iph = el.get_attribute("placeholder") or ""
            iaria = el.get_attribute("aria-label") or ""
            ival = el.input_value() if itype not in ("password",) else "***"

            # Build XPath
            xpath_parts = []
            if iid:
                xpath_parts.append(f"@id='{iid}'")
            if iname:
                xpath_parts.append(f"@name='{iname}'")
            if itype:
                xpath_parts.append(f"@type='{itype}'")

            xpath = f"//input[{ ' and '.join(xpath_parts) }]" if xpath_parts else "//input"

            findings["inputs"].append({
                "xpath": xpath,
                "type": itype,
                "name": iname,
                "id": iid,
                "placeholder": iph,
                "aria_label": iaria,
                "value_preview": (ival[:50] if ival else ""),
            })
        except Exception:
            continue

    # Textareas
    for el in page.query_selector_all("textarea"):
        try:
            if not el.is_visible():
                continue
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            iph = el.get_attribute("placeholder") or ""
            iaria = el.get_attribute("aria-label") or ""
            xpath = f"//textarea[@name='{iname}']" if iname else "//textarea"
            findings["textareas"].append({
                "xpath": xpath,
                "name": iname,
                "id": iid,
                "placeholder": iph,
                "aria_label": iaria,
            })
        except Exception:
            continue

    # Buttons
    for el in page.query_selector_all("button"):
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text() or "").strip()[:80]
            btype = el.get_attribute("type") or ""
            bclass = el.get_attribute("class") or ""
            baria = el.get_attribute("aria-label") or ""
            xpath = f"//button[contains(text(),'{text}')]" if text else "//button"
            findings["buttons"].append({
                "xpath": xpath,
                "text": text,
                "type": btype,
                "class": bclass[:100],
                "aria_label": baria,
            })
        except Exception:
            continue

    # Selects
    for el in page.query_selector_all("select"):
        try:
            if not el.is_visible():
                continue
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            xpath = f"//select[@name='{iname}']" if iname else "//select"
            findings["selects"].append({
                "xpath": xpath,
                "name": iname,
                "id": iid,
            })
        except Exception:
            continue

    # Contenteditable
    for el in page.query_selector_all("[contenteditable='true']"):
        try:
            if not el.is_visible():
                continue
            cclass = el.get_attribute("class") or ""
            crole = el.get_attribute("role") or ""
            findings["contenteditable"].append({
                "xpath": "//*[@contenteditable='true']",
                "class": cclass[:100],
                "role": crole,
            })
        except Exception:
            continue

    # Profile links (for search/visitor discovery)
    for el in page.query_selector_all("a[href]"):
        try:
            href = el.get_attribute("href") or ""
            if href.startswith("/") and not any(x in href for x in [
                "login", "settings", "search", "blog", "reviews", "interviews",
                "available", "find-massage", "live-cams", "sitemap", "advertise",
                "mailbox", "static", "_next", "images", "api", "blogs",
            ]):
                parts = href.strip("/").split("/")
                if parts and parts[0] and len(parts) == 1:
                    findings["links_profile"].append({
                        "href": href,
                        "text": (el.inner_text() or "").strip()[:60],
                    })
        except Exception:
            continue

    return findings


def detect_block(page: Page) -> Optional[str]:
    """Check for CAPTCHA / anti-bot / access blocks."""
    txt = page.inner_text("body")[:3000].lower()
    url = page.url.lower()
    needles = [
        ("captcha", "captcha_detected"),
        ("crowdsec", "crowdsec_detected"),
        ("access forbidden", "access_forbidden"),
        ("verify you are human", "human_verification"),
        ("unusual traffic", "traffic_challenge"),
        ("too many requests", "rate_limited"),
    ]
    for needle, reason in needles:
        if needle in txt or needle in url:
            return reason
    return None


def attempt_login(page: Page, username: str, password: str) -> bool:
    """Attempt login using Playwright."""
    try:
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        block = detect_block(page)
        if block:
            print(f"  BLOCKED: {block}")
            return False

        # Find email/username field
        email_selectors = [
            "input[type='email']",
            "input[name*='email' i]",
            "input[name*='user' i]",
            "input[type='text']",
        ]
        email_el = None
        for sel in email_selectors:
            email_el = page.query_selector(sel)
            if email_el and email_el.is_visible():
                break
            email_el = None

        # Find password field
        pass_el = page.query_selector("input[type='password']")

        if not email_el or not pass_el:
            print("  Login form not found")
            return False

        email_el.fill(username)
        pass_el.fill(password)
        time.sleep(0.5)

        # Click submit
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('LOG')",
            "button:has-text('Log')",
            "form button",
        ]
        for sel in submit_selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                break

        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)

        if "/login" in page.url:
            print("  Login failed — still on login page")
            return False

        print(f"  Login OK — URL: {page.url}")
        return True

    except Exception as e:
        print(f"  Login error: {e}")
        return False


def probe_page(page: Page, page_name: str, page_cfg: dict, logged_in: bool, 
               interceptor: APIInterceptor) -> dict:
    """Probe a single page: navigate, capture API, discover XPaths, screenshot."""
    print(f"\n── Probing: {page_name} ──")
    print(f"  URL: {page_cfg['url']}")

    result = {
        "page": page_name,
        "url": page_cfg["url"],
        "timestamp": now_iso(),
        "needs_login": page_cfg["needs_login"],
        "logged_in": logged_in,
    }

    # Clear API calls for this page
    interceptor.calls = []

    try:
        page.goto(page_cfg["url"], wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Detect blocks
        block = detect_block(page)
        if block:
            result["status"] = "blocked"
            result["block_reason"] = block
            print(f"  BLOCKED: {block}")
        else:
            result["status"] = "ok"
            result["title"] = page.title()
            result["final_url"] = page.url

            # Check if redirected to login
            if page_cfg["needs_login"] and "/login" in page.url:
                result["status"] = "redirected_to_login"
                result["note"] = "Page requires login — not authenticated"
                print(f"  Redirected to login")
            else:
                # Discover XPath selectors
                xpaths = discover_xpaths(page)
                result["xpaths"] = xpaths
                print(f"  Found: {len(xpaths['inputs'])} inputs, {len(xpaths['textareas'])} textareas, "
                      f"{len(xpaths['buttons'])} buttons, {len(xpaths['links_profile'])} profile links")

                # Capture __NEXT_DATA__ if present
                try:
                    next_data = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
                    if next_data:
                        result["next_data_preview"] = next_data[:2000]
                        result["next_data_len"] = len(next_data)
                        print(f"  __NEXT_DATA__: {len(next_data)} chars")
                except Exception:
                    pass

        # Screenshot
        ss_path = ARTIFACTS / "screenshots" / f"{safe_name(page_name)}.png"
        page.screenshot(path=str(ss_path), full_page=True)
        result["screenshot"] = str(ss_path)
        print(f"  Screenshot: {ss_path}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  ERROR: {e}")

    # Save API calls
    api_path = interceptor.save(page_name)
    result["api_calls"] = interceptor.calls
    result["api_calls_count"] = len(interceptor.calls)
    if interceptor.calls:
        print(f"  API calls: {len(interceptor.calls)}")
        for call in interceptor.calls[:5]:
            print(f"    {call['method']:6s} {call.get('status', '???')} {call['url'][:80]}")

    return result


def main():
    parser = argparse.ArgumentParser(description="RM API + XPath Playwright Probe")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--login", action="store_true", help="Attempt login with .env credentials")
    parser.add_argument("--page", default="all", help="Specific page to probe (or 'all')")
    args = parser.parse_args()

    # Load .env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    username = os.getenv("RM_USER") or os.getenv("RENTMASSEUR_USER") or ""
    password = os.getenv("RM_PASS") or os.getenv("RENTMASSEUR_PASS") or ""

    pages_to_probe = [args.page] if args.page != "all" else list(PAGES.keys())

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Set up API interception
        interceptor = APIInterceptor()
        context.on("request", interceptor.on_request)
        context.on("response", interceptor.on_response)

        page = context.new_page()

        # Login if requested
        logged_in = False
        if args.login and username and password:
            print(f"\n=== Attempting login as {username} ===")
            logged_in = attempt_login(page, username, password)
        elif args.login:
            print("\n!! No credentials found in .env (RM_USER / RM_PASS)")

        # Probe pages
        for page_name in pages_to_probe:
            if page_name not in PAGES:
                print(f"Unknown page: {page_name}")
                continue

            cfg = PAGES[page_name]
            result = probe_page(page, page_name, cfg, logged_in, interceptor)
            results.append(result)

        browser.close()

    # Write summary receipt
    summary = {
        "timestamp": now_iso(),
        "username": username or "(not set)",
        "login_attempted": args.login,
        "login_success": logged_in if args.login else None,
        "pages_probed": [r["page"] for r in results],
        "results": results,
    }

    receipt_path = ARTIFACTS / "probe_receipt.json"
    receipt_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # Write selector map for rm_ci/selectors.yml update
    selector_map = {}
    for r in results:
        if r.get("xpaths"):
            selector_map[r["page"]] = {
                "url": r.get("final_url", r["url"]),
                "inputs": r["xpaths"]["inputs"],
                "textareas": r["xpaths"]["textareas"],
                "buttons": r["xpaths"]["buttons"],
                "selects": r["xpaths"]["selects"],
                "contenteditable": r["xpaths"]["contenteditable"],
            }

    selector_path = ARTIFACTS / "discovered_selectors.json"
    selector_path.write_text(json.dumps(selector_map, indent=2, default=str), encoding="utf-8")

    # Write API endpoint map
    api_map = {}
    for r in results:
        if r.get("api_calls"):
            api_map[r["page"]] = [
                {
                    "method": c["method"],
                    "url": c["url"],
                    "status": c.get("status"),
                    "post_data": c.get("post_data"),
                    "response_preview": (c.get("response_body") or "")[:200],
                }
                for c in r["api_calls"]
            ]

    api_map_path = ARTIFACTS / "discovered_api_endpoints.json"
    api_map_path.write_text(json.dumps(api_map, indent=2, default=str), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Probe complete — {len(results)} pages")
    print(f"  Receipt:     {receipt_path}")
    print(f"  Selectors:   {selector_path}")
    print(f"  API endpoints: {api_map_path}")
    print(f"  Screenshots: {ARTIFACTS / 'screenshots'}/")
    print(f"  API calls:   {ARTIFACTS / 'api_calls'}/")

    # Print API summary
    total_api = sum(len(r.get("api_calls", [])) for r in results)
    print(f"\n  Total API calls captured: {total_api}")
    for r in results:
        if r.get("api_calls"):
            print(f"\n  {r['page']}:")
            for c in r["api_calls"]:
                print(f"    {c['method']:6s} {c.get('status', '???'):>4} {c['url'][:90]}")


if __name__ == "__main__":
    main()
