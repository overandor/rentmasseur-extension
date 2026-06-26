#!/usr/bin/env python3
"""
Post/update bio on RentMasseur profile.

Usage:
    python3 post_bio.py --bio-id controlled_wolf_v1
    python3 post_bio.py --file content/bios/my_bio.md
    python3 post_bio.py --text "Bio text here..."
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
BIO_URL = "https://rentmasseur.com/settings/about"
BIOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "bios")


def login(driver):
    driver.get("https://rentmasseur.com/login")
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


def post_bio(driver, bio_text):
    """Update bio on /settings/about page."""
    driver.get(BIO_URL)
    time.sleep(5)

    # Find the description textarea
    result = driver.execute_script("""
        const textareas = Array.from(document.querySelectorAll('textarea'));
        let best = null, bestScore = 0;
        for (const ta of textareas) {
            const ctx = (ta.id||'') + ' ' + (ta.name||'') + ' ' + (ta.placeholder||'');
            if (/bio|about|description|profile/i.test(ctx)) { best = ta; break; }
            if ((ta.value||'').length > bestScore) { bestScore = (ta.value||'').length; best = ta; }
        }
        if (!best && textareas.length > 0) best = textareas[0];
        if (!best) return {error: 'no_textarea', count: textareas.length};
        
        const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        ns.call(best, arguments[0]);
        best.dispatchEvent(new Event('input', {bubbles: true}));
        best.dispatchEvent(new Event('change', {bubbles: true}));
        best.dispatchEvent(new Event('blur', {bubbles: true}));
        
        return {id: best.id, name: best.name, old_len: bestScore, new_len: arguments[0].length};
    """, bio_text)

    if isinstance(result, dict) and 'error' in result:
        return False, result

    time.sleep(1)

    # Save
    saved = driver.execute_script("""
        const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
        const sb = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
        if (sb) { sb.click(); return {ok: true, text: sb.innerText || sb.value}; }
        return {ok: false};
    """)
    time.sleep(5)

    return saved.get('ok', False), {"bio_update": result, "save": saved}


def write_receipt(action, data, success=True):
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {"action": action, "success": success, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    rpath = os.path.join(receipts_dir, f"{action}_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    return rpath


def main():
    parser = argparse.ArgumentParser(description="Post bio to RentMasseur")
    parser.add_argument("--bio-id", required=False, help="Bio ID from content/bios/ (e.g. controlled_wolf_v1)")
    parser.add_argument("--file", required=False, help="Read bio from file")
    parser.add_argument("--text", required=False, help="Bio text directly")
    args = parser.parse_args()

    bio_text = ""
    bio_id = "custom"

    if args.bio_id:
        path = os.path.join(BIOS_DIR, f"{args.bio_id}.md")
        if not os.path.exists(path):
            print(f"Error: {path} not found")
            sys.exit(1)
        with open(path, "r") as f:
            bio_text = f.read().strip()
        bio_id = args.bio_id
    elif args.file:
        with open(args.file, "r") as f:
            bio_text = f.read().strip()
        bio_id = os.path.basename(args.file).replace(".md", "")
    elif args.text:
        bio_text = args.text
    else:
        print("Error: --bio-id, --file, or --text required")
        sys.exit(1)

    print(f"Bio ID: {bio_id}")
    print(f"Bio length: {len(bio_text)} chars")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=149)

    try:
        print("\n[1] Login...")
        if not login(driver):
            print("  Login failed!")
            sys.exit(1)

        print("\n[2] Posting bio...")
        success, details = post_bio(driver, bio_text)

        rpath = write_receipt("post_bio", {"bio_id": bio_id, "bio_len": len(bio_text), "details": details}, success)
        if success:
            print(f"\n=== BIO POSTED === Receipt: {rpath}")
        else:
            print(f"\n=== BIO POST FAILED === Receipt: {rpath}")
            sys.exit(1)

    finally:
        driver.quit()
        print("\nDone.")


if __name__ == "__main__":
    main()
