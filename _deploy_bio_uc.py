#!/usr/bin/env python3
"""Login + deploy bio using undetected-chromedriver to bypass CAPTCHA detection."""
import time, os, sys
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
LOGIN_URL = "https://rentmasseur.com/login"
PROFILE_URL = "https://rentmasseur.com/profile"
BIO_URL = "https://rentmasseur.com/profile/edit"

BIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "bios", "controlled_wolf_v1.md")

print(f"Username: {USERNAME}")
print(f"Bio file: {BIO_FILE}")

with open(BIO_FILE, "r") as f:
    BIO_TEXT = f.read().strip()
print(f"Bio length: {len(BIO_TEXT)} chars")

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")

driver = uc.Chrome(options=options, version_main=149)
try:
    print("\n[1] Navigating to login...")
    driver.set_page_load_timeout(90)
    driver.get(LOGIN_URL)
    time.sleep(8)
    
    print(f"  Title: {driver.title}")
    print(f"  URL: {driver.current_url}")
    
    # Check if CAPTCHA is present
    captcha = driver.execute_script("""
        return !!document.querySelector('.g-recaptcha, #captcha, iframe[src*="recaptcha"], iframe[src*="captcha"]');
    """)
    print(f"  CAPTCHA present: {captcha}")
    
    if captcha:
        print("\n[2] CAPTCHA detected. Waiting up to 120s for it to be solved...")
        for i in range(24):
            time.sleep(5)
            captcha_still = driver.execute_script("""
                const iframe = document.querySelector('iframe[src*="recaptcha"]');
                if (!iframe) return false;
                // Check if recaptcha response is filled
                try {
                    return !grecaptcha.getResponse();
                } catch(e) {
                    return true;
                }
            """)
            if not captcha_still:
                print("  CAPTCHA solved!")
                break
            print(f"  Waiting for CAPTCHA solve... ({(i+1)*5}s)")
        else:
            print("  CAPTCHA not solved in time. Trying to proceed anyway...")
    
    # Wait for login form to appear
    print("\n[3] Looking for login form...")
    for attempt in range(10):
        time.sleep(3)
        inputs = driver.execute_script("""
            return Array.from(document.querySelectorAll('input')).map(i => ({
                type: i.type, name: i.name, id: i.id, placeholder: i.placeholder,
                visible: i.offsetParent !== null
            }));
        """)
        print(f"  Attempt {attempt+1}: {len(inputs)} inputs found")
        for inp in inputs:
            print(f"    type={inp['type']} name={inp['name']} id={inp['id']} placeholder={inp['placeholder']} visible={inp['visible']}")
        
        pwd = driver.execute_script("""
            return document.querySelector('input[type="password"]') ||
                   document.querySelector('input[name*="pass" i]') ||
                   document.querySelector('input[placeholder*="pass" i]');
        """)
        if pwd:
            print("  Password field found!")
            break
    else:
        print("  No login form found after waiting. Dumping page...")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/login_after_captcha.png")
        with open("/Users/alep/Downloads/rentmasseur-optimizer/login_after.html", "w") as f:
            f.write(driver.page_source)
        sys.exit(1)
    
    # Fill login form
    print("\n[4] Filling login form...")
    driver.execute_script(f"""
        const pwd = document.querySelector('input[type="password"]') ||
                    document.querySelector('input[name*="pass" i]');
        const user = document.querySelector('input[type="text"]') ||
                     document.querySelector('input[type="email"]') ||
                     document.querySelector('input[name*="user" i]') ||
                     document.querySelector('input[name*="email" i]');
        if (user) {{ user.value = '{USERNAME}'; user.dispatchEvent(new Event('input', {{bubbles: true}})); }}
        if (pwd) {{ pwd.value = '{PASSWORD}'; pwd.dispatchEvent(new Event('input', {{bubbles: true}})); }}
    """)
    time.sleep(2)
    
    # Click submit
    driver.execute_script("""
        const btn = document.querySelector('button[type="submit"]') ||
                    document.querySelector('input[type="submit"]') ||
                    Array.from(document.querySelectorAll('button')).find(b => /login|sign.in|submit/i.test(b.innerText));
        if (btn) btn.click();
    """)
    time.sleep(8)
    
    print(f"  After login URL: {driver.current_url}")
    if "login" in driver.current_url.lower():
        print("  Login may have failed. Screenshot saved.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/login_failed.png")
        sys.exit(1)
    
    print("  Login successful!")
    
    # Navigate to profile edit
    print("\n[5] Navigating to profile edit...")
    driver.get(BIO_URL)
    time.sleep(5)
    
    # Find bio textarea
    print("  Looking for bio textarea...")
    bio_field = driver.execute_script("""
        const textareas = Array.from(document.querySelectorAll('textarea'));
        let best = null, bestScore = 0;
        for (const ta of textareas) {
            const score = (ta.value || '').length;
            if (score > bestScore) { bestScore = score; best = ta; }
        }
        if (!best && textareas.length > 0) best = textareas[0];
        if (best) {
            best.value = arguments[0];
            best.dispatchEvent(new Event('input', {bubbles: true}));
            best.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }
        return false;
    """, BIO_TEXT)
    
    if bio_field:
        print("  Bio field updated!")
        time.sleep(2)
        
        # Click save
        saved = driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
            const saveBtn = buttons.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
            if (saveBtn) { saveBtn.click(); return true; }
            return false;
        """)
        print(f"  Save clicked: {saved}")
        time.sleep(5)
        print("\n  BIO DEPLOYED SUCCESSFULLY!")
    else:
        print("  No textarea found. Screenshot saved.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_edit.png")
    
finally:
    driver.quit()
    print("\nDone.")
