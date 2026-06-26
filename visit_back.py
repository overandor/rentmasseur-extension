#!/usr/bin/env python3
"""
Visit-back automation: scrape visitors from /settings/whosawme,
then visit each visitor's profile page to increase visibility.

Usage:
    python3 visit_back.py --dry-run    # list visitors without visiting
    python3 visit_back.py              # visit all visitors
    python3 visit_back.py --limit 20   # visit max 20
"""
import time, os, sys, json, argparse
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from datetime import datetime, timezone

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
WHOSAWME_URL = "https://rentmasseur.com/settings/whosawme"
BASE_URL = "https://rentmasseur.com"


def login(driver):
    driver.get(f"{BASE_URL}/login")
    time.sleep(6)
    driver.execute_script("""
        const pwd = document.querySelector('input[type="password"]');
        const user = document.querySelector('input[type="text"], input[type="email"]');
        const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
        if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
    """, USERNAME, PASSWORD)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys(Keys.ENTER)
    time.sleep(5)
    return "login" not in driver.current_url.lower()


def scrape_visitors(driver):
    """Scrape list of visitors from /settings/whosawme."""
    driver.get(WHOSAWME_URL)
    time.sleep(5)

    visitors = driver.execute_script("""
        const result = [];
        const seen = new Set();
        
        // Method 1: Find profile photo links (img alt="Profile photo" inside <a>)
        const profileImgs = document.querySelectorAll('img[alt="Profile photo"], img[alt="profile-picture"]');
        for (const img of profileImgs) {
            const a = img.closest('a');
            if (a && a.href) {
                const path = new URL(a.href).pathname;
                const username = path.replace('/', '');
                if (username && !seen.has(username) && !username.includes('settings') && !username.includes('gay-massage')) {
                    seen.add(username);
                    result.push({username: username, url: a.href, name: username});
                }
            }
        }
        
        // Method 2: Find links to /username patterns (not settings/gay-massage/etc)
        const links = Array.from(document.querySelectorAll('a[href]'));
        for (const a of links) {
            const href = a.href;
            if (!href.startsWith('https://rentmasseur.com/')) continue;
            const path = new URL(href).pathname;
            // Single-segment paths = usernames (e.g. /Jerbolt)
            if (path && path !== '/' && path.split('/').length === 2 && path.split('/')[1] !== '') {
                const username = path.replace('/', '');
                if (!seen.has(username) && 
                    !['settings','gay-massage','stream','masseurcams','advertise','about','login','sitemap','topics','robots','api'].includes(username) &&
                    !username.startsWith('_') &&
                    username.length > 2) {
                    seen.add(username);
                    result.push({username: username, url: href, name: username});
                }
            }
        }
        
        return result;
    """)
    return visitors


def visit_profile(driver, visitor_url):
    """Visit a visitor's profile page."""
    driver.get(visitor_url)
    time.sleep(3)
    return driver.current_url


def write_receipt(action, data, success=True):
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {
        "action": action,
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data
    }
    rpath = os.path.join(receipts_dir, f"{action}_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    return rpath


def main():
    parser = argparse.ArgumentParser(description="Visit back everyone who visited your profile")
    parser.add_argument("--dry-run", action="store_true", help="List visitors without visiting")
    parser.add_argument("--limit", type=int, default=50, help="Max visitors to visit")
    args = parser.parse_args()

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=149)

    try:
        print("[1] Login...")
        if not login(driver):
            print("  Login failed!")
            sys.exit(1)
        print(f"  OK: {driver.current_url}")

        print("\n[2] Scraping visitors from /settings/whosawme...")
        visitors = scrape_visitors(driver)
        print(f"  Found {len(visitors)} visitors")
        for v in visitors[:10]:
            print(f"    {v['name']} -> {v['url']}")

        if args.dry_run:
            print(f"\n  Dry run — would visit {min(len(visitors), args.limit)} profiles")
            write_receipt("visit_back", {"visitors_found": len(visitors), "dry_run": True, "visitor_list": visitors[:args.limit]})
            return

        print(f"\n[3] Visiting {min(len(visitors), args.limit)} profiles...")
        visited = []
        for i, v in enumerate(visitors[:args.limit]):
            print(f"  [{i+1}/{min(len(visitors), args.limit)}] Visiting {v['name']}...")
            url = visit_profile(driver, v['url'])
            visited.append({"username": v['username'], "url": v['url'], "visited_at": datetime.now(timezone.utc).isoformat()})
            time.sleep(2)

        rpath = write_receipt("visit_back", {
            "visitors_found": len(visitors),
            "visited_count": len(visited),
            "visited": visited
        })
        print(f"\n=== VISITED {len(visited)} PROFILES === Receipt: {rpath}")

    finally:
        driver.quit()
        print("\nDone.")


if __name__ == "__main__":
    main()
