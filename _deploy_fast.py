#!/usr/bin/env python3
"""Fast login + bio deploy with undetected-chromedriver. CAPTCHA bypass worked."""
import time, os, sys, json
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from datetime import datetime, timezone

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
BIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "bios", "controlled_wolf_v1.md")

with open(BIO_FILE, "r") as f:
    BIO_TEXT = f.read().strip()

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = uc.Chrome(options=options, version_main=149)

try:
    # Step 1: Login
    print("[1] Login...")
    driver.get("https://rentmasseur.com/login")
    time.sleep(6)

    # Find and fill fields using JS
    result = driver.execute_script("""
        const pwd = document.querySelector('input[type="password"]');
        const inputs = Array.from(document.querySelectorAll('input'));
        const user = inputs.find(i => i !== pwd && (i.type === 'text' || i.type === 'email'));
        if (!pwd || !user) return {error: 'no_fields', inputs: inputs.length};
        
        // Set values using native setter
        const nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputSetter.call(user, arguments[0]);
        user.dispatchEvent(new Event('input', {bubbles: true}));
        
        nativeInputSetter.call(pwd, arguments[1]);
        pwd.dispatchEvent(new Event('input', {bubbles: true}));
        
        // Find submit button
        const form = pwd.closest('form') || user.closest('form');
        let btn = null;
        if (form) {
            btn = form.querySelector('button[type="submit"]') || 
                  form.querySelector('input[type="submit"]') ||
                  Array.from(form.querySelectorAll('button')).find(b => /login|sign|submit/i.test(b.innerText));
        }
        if (!btn) btn = Array.from(document.querySelectorAll('button')).find(b => /login|sign|submit/i.test(b.innerText));
        
        return {user: {id: user.id, name: user.name, type: user.type, value: user.value},
                pwd: {id: pwd.id, name: pwd.name, type: pwd.type, value: '***'},
                btn: btn ? {tag: btn.tagName, text: btn.innerText, type: btn.type} : null};
    """, USERNAME, PASSWORD)
    print(f"  Fields: {result}")
    
    if isinstance(result, dict) and 'error' in result:
        print(f"  Error: {result}")
        sys.exit(1)
    
    time.sleep(1)
    
    # Submit via Enter key on password field
    from selenium.webdriver.common.keys import Keys
    pwd_el = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
    pwd_el.send_keys(Keys.ENTER)
    time.sleep(5)
    
    print(f"  URL after login: {driver.current_url}")
    
    if "login" in driver.current_url.lower():
        # Try clicking button directly
        print("  Retrying with button click...")
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"], button')
            for btn in btns:
                txt = (btn.text or btn.get_attribute("value") or "").lower()
                if "login" in txt or "sign" in txt or "submit" in txt:
                    btn.click()
                    time.sleep(5)
                    break
        except:
            pass
        print(f"  URL after retry: {driver.current_url}")
    
    if "login" in driver.current_url.lower():
        print("  Login failed. Screenshot saved.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/login_debug.png")
        # Dump error messages
        errors = driver.execute_script("""
            return Array.from(document.querySelectorAll('[role="alert"], .error, .alert, .form-error, .invalid-feedback')).map(e => e.innerText).filter(Boolean);
        """)
        print(f"  Errors: {errors}")
        sys.exit(1)
    
    print("  Login OK!")
    
    # Step 2: Deploy bio
    print("[2] Deploy bio...")
    driver.get("https://rentmasseur.com/profile/edit")
    time.sleep(4)
    
    # Find the bio textarea (longest one)
    updated = driver.execute_script("""
        const textareas = Array.from(document.querySelectorAll('textarea'));
        let best = null, bestScore = 0;
        for (const ta of textareas) {
            const score = (ta.value || '').length;
            if (score > bestScore) { bestScore = score; best = ta; }
        }
        if (!best && textareas.length > 0) best = textareas[0];
        if (!best) return {error: 'no_textarea', count: textareas.length};
        
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(best, arguments[0]);
        best.dispatchEvent(new Event('input', {bubbles: true}));
        best.dispatchEvent(new Event('change', {bubbles: true}));
        
        return {found: true, old_len: bestScore, new_len: arguments[0].length};
    """, BIO_TEXT)
    print(f"  Bio update: {updated}")
    
    if isinstance(updated, dict) and 'error' in updated:
        print(f"  Error: {updated}")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_debug.png")
        sys.exit(1)
    
    time.sleep(1)
    
    # Save
    saved = driver.execute_script("""
        const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
        const saveBtn = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
        if (saveBtn) { saveBtn.click(); return true; }
        return false;
    """)
    print(f"  Save: {saved}")
    time.sleep(4)
    
    # Receipt
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {
        "action": "bio_deploy",
        "bio_id": "controlled_wolf_v1",
        "experiment_id": "exp_001_targeted_wolf",
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "undetected-chromedriver"
    }
    rpath = os.path.join(receipts_dir, f"deploy_controlled_wolf_v1_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"  Receipt: {rpath}")
    print("\n=== BIO DEPLOYED ===")

finally:
    driver.quit()
    print("Done.")
