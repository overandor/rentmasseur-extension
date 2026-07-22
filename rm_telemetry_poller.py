#!/usr/bin/env python3
"""
RM Telemetry Poller — lightweight 1-minute visitor polling.

Logs in once, scrapes "who saw me" every 60 seconds for N minutes,
writes telemetry snapshots to content/telemetry.jsonl, and updates
content/telemetry_latest.json with the current state.

Designed for GitHub Actions 5-min cron with 10-min run duration.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://rentmasseur.com"
CONTENT_DIR = Path("content")
TELEMETRY_LATEST = CONTENT_DIR / "telemetry_latest.json"
TELEMETRY_LOG = CONTENT_DIR / "telemetry.jsonl"

EXCLUDE = {
    'settings', 'gay-massage', 'stream', 'masseurcams', 'advertise',
    'about', 'login', 'sitemap', 'topics', 'robots', 'api', 'blog',
    'blogs', 'reviews', 'interviews', 'find-massage', 'live-cams',
    'available', 'static', '_next', 'images', 'mailbox', 'compose',
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env():
    from pathlib import Path
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def write_receipt(action: str, status: str, data: dict):
    receipts_dir = Path("receipts")
    receipts_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    receipt = {"action": action, "status": status, "timestamp": now_iso(), **data}
    path = receipts_dir / f"telemetry_{action}_{ts}.json"
    path.write_text(json.dumps(receipt, indent=2))
    print(f"  Receipt: {path}")


def login(driver, username: str, password: str) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    print("=== LOGIN ===")
    driver.get(f"{BASE_URL}/login")
    time.sleep(random.uniform(3, 5))

    inputs = driver.find_elements(By.CSS_SELECTOR, "input")
    email_el = pass_el = None
    for inp in inputs:
        if not inp.is_displayed():
            continue
        itype = (inp.get_attribute("type") or "").lower()
        iname = (inp.get_attribute("name") or "").lower()
        if itype == "password":
            pass_el = inp
        elif "email" in iname or "user" in iname or itype in ("email", "text"):
            email_el = inp

    if not email_el or not pass_el:
        print("Login form not found", file=sys.stderr)
        write_receipt("login", "fail", {"reason": "form_not_found"})
        return False

    email_el.click()
    time.sleep(0.5)
    for char in username:
        email_el.send_keys(char)
        time.sleep(random.uniform(0.05, 0.12))

    pass_el.click()
    time.sleep(0.3)
    for char in password:
        pass_el.send_keys(char)
        time.sleep(random.uniform(0.05, 0.12))

    pass_el.send_keys(Keys.ENTER)
    time.sleep(random.uniform(4, 6))

    if "/login" in driver.current_url.lower():
        print("Login failed — still on login page", file=sys.stderr)
        write_receipt("login", "fail", {"reason": "still_on_login", "url": driver.current_url})
        return False

    print(f"Login OK — URL: {driver.current_url}")
    write_receipt("login", "pass", {"url": driver.current_url})
    return True


def scrape_visitors(driver) -> list[dict]:
    """Scrape the 'who saw me' page for current visitor list."""
    from selenium.webdriver.common.by import By

    driver.get(f"{BASE_URL}/settings/whosawme")
    time.sleep(random.uniform(2, 4))

    visitors = driver.execute_script("""
        const result = [];
        const seen = new Set();
        const profileImgs = document.querySelectorAll('img[alt="Profile photo"], img[alt="profile-picture"]');
        for (const img of profileImgs) {
            const a = img.closest('a');
            if (a && a.href) {
                const path = new URL(a.href).pathname;
                const username = path.replace('/', '');
                if (username && !seen.has(username) && !username.includes('settings') && !username.includes('gay-massage')) {
                    seen.add(username);
                    result.push({username: username, url: a.href});
                }
            }
        }
        const links = Array.from(document.querySelectorAll('a[href]'));
        for (const a of links) {
            const href = a.href;
            if (!href.startsWith('https://rentmasseur.com/')) continue;
            const path = new URL(href).pathname;
            if (path && path !== '/' && path.split('/').length === 2 && path.split('/')[1] !== '') {
                const username = path.replace('/', '');
                if (!seen.has(username) && !username.startsWith('_') && username.length > 2) {
                    seen.add(username);
                    result.push({username: username, url: href});
                }
            }
        }
        return result;
    """)

    filtered = [v for v in visitors if v["username"] not in EXCLUDE]
    return filtered


def scrape_online_count(driver) -> int:
    """Try to extract number of currently online users from the page."""
    try:
        text = driver.execute_script("return document.body ? document.body.innerText : ''")
        for line in text.split("\n"):
            line = line.strip().lower()
            if "online now" in line or "currently online" in line:
                import re
                m = re.search(r'(\d+)\s+(?:users?\s+)?online', line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0


def scrape_messages_count(driver) -> int:
    """Try to extract unread message count from nav badge."""
    try:
        badges = driver.execute_script("""
            const badges = document.querySelectorAll('.badge, .notification-badge, .msg-count, [class*="badge"]');
            let max = 0;
            for (const b of badges) {
                const txt = b.textContent.trim();
                const n = parseInt(txt);
                if (!isNaN(n) && n > max) max = n;
            }
            return max;
        """)
        return badges or 0
    except Exception:
        return 0


def poll_once(driver, poll_num: int) -> dict:
    """Single telemetry poll — scrape visitors, online count, messages."""
    ts = now_iso()
    print(f"\n--- Poll #{poll_num} at {ts} ---")

    visitors = scrape_visitors(driver)
    online_count = scrape_online_count(driver)
    unread_messages = scrape_messages_count(driver)

    visitor_names = [v["username"] for v in visitors]

    snapshot = {
        "poll_num": poll_num,
        "timestamp": ts,
        "visitor_count": len(visitors),
        "visitors": visitor_names,
        "online_count": online_count,
        "unread_messages": unread_messages,
    }

    # Append to JSONL log
    with open(TELEMETRY_LOG, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    # Update latest snapshot
    TELEMETRY_LATEST.write_text(json.dumps(snapshot, indent=2))

    print(f"  Visitors: {len(visitors)} | Online: {online_count} | Unread: {unread_messages}")
    print(f"  New visitors: {', '.join(visitor_names[:5])}{'...' if len(visitor_names) > 5 else ''}")

    return snapshot


def main():
    import argparse
    parser = argparse.ArgumentParser(description="RM Telemetry Poller")
    parser.add_argument("--duration", type=int, default=600, help="Total run duration in seconds (default: 600 = 10 min)")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds (default: 60)")
    parser.add_argument("--max-load-more", type=int, default=5, help="Max Load More clicks per poll (default: 5)")
    args = parser.parse_args()

    load_env()

    username = os.environ.get("RENTMASSEUR_USERNAME")
    password = os.environ.get("RENTMASSEUR_PASSWORD")
    if not username or not password:
        print("ERROR: RENTMASSEUR_USERNAME and RENTMASSEUR_PASSWORD required", file=sys.stderr)
        sys.exit(1)

    CONTENT_DIR.mkdir(exist_ok=True)

    # Setup Chrome
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        print("Installing undetected-chromedriver...")
        os.system(f"{sys.executable} -m pip install undetected-chromedriver selenium")
        import undetected_chromedriver as uc
        from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(30)

    try:
        if not login(driver, username, password):
            print("Login failed, exiting", file=sys.stderr)
            sys.exit(1)

        start = time.time()
        poll_num = 0
        all_snapshots = []

        while time.time() - start < args.duration:
            poll_num += 1
            try:
                snapshot = poll_once(driver, poll_num)
                all_snapshots.append(snapshot)
            except Exception as e:
                print(f"  Poll error: {e}", file=sys.stderr)
                write_receipt("poll", "error", {"poll_num": poll_num, "error": str(e)})

            elapsed = time.time() - start
            remaining = args.duration - elapsed
            if remaining < args.interval:
                break
            print(f"  Sleeping {args.interval}s until next poll... ({remaining:.0f}s remaining)")
            time.sleep(args.interval)

        # Summary
        total_visitors_seen = set()
        for s in all_snapshots:
            total_visitors_seen.update(s.get("visitors", []))

        summary = {
            "action": "telemetry_poll",
            "timestamp": now_iso(),
            "polls_completed": len(all_snapshots),
            "duration_seconds": int(time.time() - start),
            "interval_seconds": args.interval,
            "unique_visitors": len(total_visitors_seen),
            "all_visitors": sorted(total_visitors_seen),
            "max_online": max((s.get("online_count", 0) for s in all_snapshots), default=0),
            "max_unread_messages": max((s.get("unread_messages", 0) for s in all_snapshots), default=0),
        }

        write_receipt("telemetry_poll", "pass", summary)
        print(f"\n=== SUMMARY ===")
        print(f"Polls: {len(all_snapshots)}")
        print(f"Unique visitors: {len(total_visitors_seen)}")
        print(f"Max online: {summary['max_online']}")
        print(f"Max unread: {summary['max_unread_messages']}")

    finally:
        driver.quit()
        print("Driver closed.")


if __name__ == "__main__":
    main()
