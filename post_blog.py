#!/usr/bin/env python3
"""
Post a blog entry to RentMasseur profile.

Usage:
    python3 post_blog.py --title "My Title" --content "Blog body text..."
    python3 post_blog.py --file content/blog/post.md
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
BLOG_URL = "https://rentmasseur.com/settings/blog"


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


def post_blog(driver, title, content):
    """Navigate to blog settings and post a new entry."""
    driver.get(BLOG_URL)
    time.sleep(5)

    # Look for "New Post" or "Add" button
    print("  Looking for new post button...")
    clicked = driver.execute_script("""
        const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        const newBtn = btns.find(b => /new|add|create|write|post/i.test(b.innerText || b.textContent || ''));
        if (newBtn) { newBtn.click(); return true; }
        return false;
    """)
    if clicked:
        time.sleep(3)

    # Find title input and content textarea
    print("  Looking for form fields...")
    fields = driver.execute_script("""
        const r = {inputs: [], textareas: []};
        document.querySelectorAll('input').forEach(i => r.inputs.push({type:i.type,id:i.id,name:i.name,ph:i.placeholder,vis:i.offsetParent!==null}));
        document.querySelectorAll('textarea').forEach(t => r.textareas.push({id:t.id,name:t.name,ph:t.placeholder,vis:t.offsetParent!==null,val:(t.value||'').substring(0,50)}));
        return r;
    """)
    print(f"  Inputs: {len(fields['inputs'])}, Textareas: {len(fields['textareas'])}")

    # Fill title (first visible text input) and content (first visible textarea)
    result = driver.execute_script("""
        const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.offsetParent !== null && (i.type === 'text' || i.type === 'title'));
        const textareas = Array.from(document.querySelectorAll('textarea')).filter(t => t.offsetParent !== null);
        
        const titleInput = inputs.find(i => /title|subject|headline/i.test(i.name + i.id + i.placeholder)) || inputs[0];
        const contentArea = textareas.find(t => /content|body|post|message|text/i.test(t.name + t.id + t.placeholder)) || textareas[0];
        
        if (!titleInput || !contentArea) return {error: 'no_fields', inputs: inputs.length, textareas: textareas.length};
        
        const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        ns.call(titleInput, arguments[0]);
        titleInput.dispatchEvent(new Event('input', {bubbles: true}));
        
        const tns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        tns.call(contentArea, arguments[1]);
        contentArea.dispatchEvent(new Event('input', {bubbles: true}));
        contentArea.dispatchEvent(new Event('change', {bubbles: true}));
        
        return {title_id: titleInput.id, content_id: contentArea.id, title_len: arguments[0].length, content_len: arguments[1].length};
    """, title, content)
    print(f"  Fill result: {result}")

    if isinstance(result, dict) and 'error' in result:
        return False, result

    time.sleep(1)

    # Click publish/post/submit
    saved = driver.execute_script("""
        const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
        const sb = btns.find(b => /post|publish|submit|save|add|create/i.test((b.innerText||'') + ' ' + (b.value||'')));
        if (sb) { sb.click(); return {ok: true, text: sb.innerText || sb.value}; }
        return {ok: false};
    """)
    print(f"  Submit: {saved}")
    time.sleep(5)

    return saved.get('ok', False), saved


def write_receipt(action, data, success=True):
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {"action": action, "success": success, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    rpath = os.path.join(receipts_dir, f"{action}_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    return rpath


def main():
    parser = argparse.ArgumentParser(description="Post a blog entry to RentMasseur")
    parser.add_argument("--title", required=False, help="Blog title")
    parser.add_argument("--content", required=False, help="Blog content text")
    parser.add_argument("--file", required=False, help="Read content from file (first line = title, rest = body)")
    args = parser.parse_args()

    title = args.title or ""
    content = args.content or ""

    if args.file:
        with open(args.file, "r") as f:
            lines = f.read().strip().split("\n")
        title = lines[0] if lines else ""
        content = "\n".join(lines[1:]) if len(lines) > 1 else ""

    if not title or not content:
        print("Error: --title and --content required (or --file)")
        sys.exit(1)

    print(f"Title: {title[:60]}")
    print(f"Content: {len(content)} chars")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=149)

    try:
        print("\n[1] Login...")
        if not login(driver):
            print("  Login failed!")
            sys.exit(1)

        print("\n[2] Posting blog...")
        success, details = post_blog(driver, title, content)

        rpath = write_receipt("post_blog", {"title": title, "content_len": len(content), "details": details}, success)
        if success:
            print(f"\n=== BLOG POSTED === Receipt: {rpath}")
        else:
            print(f"\n=== BLOG POST FAILED === Receipt: {rpath}")
            sys.exit(1)

    finally:
        driver.quit()
        print("\nDone.")


if __name__ == "__main__":
    main()
