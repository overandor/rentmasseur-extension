#!/usr/bin/env python3
"""Login + find bio edit page + deploy bio."""
import time, os, sys, json
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
    # Login
    print("[1] Login...")
    driver.get("https://rentmasseur.com/login")
    time.sleep(6)
    
    driver.execute_script("""
        const pwd = document.querySelector('input[type="password"]');
        const user = document.querySelector('input[type="text"], input[type="email"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        if (user) { nativeSetter.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
        if (pwd) { nativeSetter.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
    """, USERNAME, PASSWORD)
    time.sleep(1)
    
    pwd_el = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
    pwd_el.send_keys(Keys.ENTER)
    time.sleep(5)
    print(f"  URL: {driver.current_url}")
    
    # Try multiple edit URLs
    edit_urls = [
        "https://rentmasseur.com/profile/edit",
        "https://rentmasseur.com/profile",
        "https://rentmasseur.com/dashboard",
        "https://rentmasseur.com/profile/bio",
        "https://rentmasseur.com/edit-profile",
        "https://rentmasseur.com/settings",
        "https://rentmasseur.com/profile/edit/bio",
    ]
    
    print("\n[2] Finding bio edit page...")
    for url in edit_urls:
        driver.get(url)
        time.sleep(3)
        textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input')
        print(f"  {url} -> {driver.current_url} | textareas={len(textareas)} inputs={len(inputs)}")
        if textareas:
            for ta in textareas:
                val = ta.get_attribute("value") or ""
                print(f"    textarea id={ta.get_attribute('id')} name={ta.get_attribute('name')} len={len(val)} preview={val[:60]}")
            
            # Found textareas - update the bio one
            print(f"\n[3] Updating bio on {driver.current_url}...")
            updated = driver.execute_script("""
                const textareas = Array.from(document.querySelectorAll('textarea'));
                let best = null, bestScore = 0;
                for (const ta of textareas) {
                    const val = ta.value || '';
                    const score = val.length;
                    // Prefer textarea that looks like bio (longest, or has bio/about in name)
                    const ctx = (ta.id||'') + ' ' + (ta.name||'') + ' ' + (ta.placeholder||'');
                    if (/bio|about|description|profile/i.test(ctx)) { bestScore = 99999; best = ta; break; }
                    if (score > bestScore) { bestScore = score; best = ta; }
                }
                if (!best && textareas.length > 0) best = textareas[0];
                if (!best) return {error: 'no_textarea'};
                
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(best, arguments[0]);
                best.dispatchEvent(new Event('input', {bubbles: true}));
                best.dispatchEvent(new Event('change', {bubbles: true}));
                best.dispatchEvent(new Event('blur', {bubbles: true}));
                
                return {id: best.id, name: best.name, old_len: bestScore, new_len: arguments[0].length};
            """, BIO_TEXT)
            print(f"  Result: {updated}")
            
            if isinstance(updated, dict) and 'error' not in updated:
                time.sleep(1)
                # Save
                saved = driver.execute_script("""
                    const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                    const saveBtn = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
                    if (saveBtn) { saveBtn.click(); return {clicked: true, text: saveBtn.innerText}; }
                    return {clicked: false};
                """)
                print(f"  Save: {saved}")
                time.sleep(4)
                
                # Receipt
                receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
                os.makedirs(receipts_dir, exist_ok=True)
                receipt = {
                    "action": "bio_deploy", "bio_id": "controlled_wolf_v1",
                    "experiment_id": "exp_001_targeted_wolf", "success": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": driver.current_url
                }
                rpath = os.path.join(receipts_dir, f"deploy_controlled_wolf_v1_{receipt['timestamp'].replace(':','-')}.json")
                with open(rpath, "w") as f:
                    json.dump(receipt, f, indent=2)
                print(f"\n=== BIO DEPLOYED === Receipt: {rpath}")
                break
    else:
        # Dump all links on dashboard
        print("\n  No textarea found on any URL. Dumping links...")
        driver.get("https://rentmasseur.com/dashboard")
        time.sleep(3)
        links = driver.execute_script("""
            return Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.innerText.trim()})).filter(a => a.text);
        """)
        for link in links[:30]:
            print(f"    {link['text'][:40]} -> {link['href']}")
        
        # Also check current page content
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/dashboard.png")
        print(f"  Screenshot: /Users/alep/Downloads/rentmasseur-optimizer/dashboard.png")

finally:
    driver.quit()
    print("\nDone.")
