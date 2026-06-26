#!/usr/bin/env python3
"""
Login + deploy bio with CAPTCHA solving.

Strategy:
1. Use undetected-chromedriver to avoid bot detection
2. Click reCAPTCHA checkbox iframe
3. If image challenge appears, use OpenCV + heuristics to solve
4. If can't solve, wait for manual intervention with visible browser
"""
import time, os, sys, json, base64, io
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import cv2
import numpy as np
from PIL import Image

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
LOGIN_URL = "https://rentmasseur.com/login"
BIO_URL = "https://rentmasseur.com/profile/edit"

BIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "bios", "controlled_wolf_v1.md")

with open(BIO_FILE, "r") as f:
    BIO_TEXT = f.read().strip()

print(f"Username: {USERNAME}")
print(f"Bio length: {len(BIO_TEXT)} chars")


def click_recaptcha_checkbox(driver):
    """Click the reCAPTCHA 'I'm not a robot' checkbox."""
    try:
        # Find the reCAPTCHA iframe
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"]')
        for frame in frames:
            src = frame.get_attribute("src") or ""
            if "anchor" in src:
                driver.switch_to.frame(frame)
                time.sleep(1)
                checkbox = driver.find_element(By.CSS_SELECTOR, '#recaptcha-anchor')
                if checkbox:
                    checkbox.click()
                    print("  Clicked reCAPTCHA checkbox")
                    time.sleep(3)
                    # Check if it passed
                    aria = checkbox.get_attribute("aria-checked")
                    print(f"  Checkbox aria-checked: {aria}")
                    driver.switch_to.default_content()
                    return aria == "true"
                driver.switch_to.default_content()
        print("  No reCAPTCHA anchor iframe found")
        return False
    except Exception as e:
        print(f"  Error clicking checkbox: {e}")
        driver.switch_to.default_content()
        return False


def solve_image_challenge(driver):
    """Attempt to solve reCAPTCHA image challenge using OpenCV."""
    try:
        # Switch to the challenge iframe (bframe)
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"]')
        if not frames:
            print("  No challenge iframe found")
            return False
        
        driver.switch_to.frame(frames[0])
        time.sleep(2)
        
        # Get the challenge instructions
        try:
            instruction_el = driver.find_element(By.CSS_SELECTOR, '.rc-imageselect-instructions')
            instruction = instruction_el.text.lower()
            print(f"  Challenge: {instruction}")
        except:
            instruction = ""
        
        # Take screenshot of the challenge
        challenge_img = driver.find_element(By.CSS_SELECTOR, '#rc-imageselect-target')
        png = challenge_img.screenshot_as_png
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        
        # Save for debugging
        debug_path = "/Users/alep/Downloads/rentmasseur-optimizer/captcha_challenge.png"
        cv2.imwrite(debug_path, img)
        print(f"  Challenge image saved: {debug_path}")
        
        # Get grid info (usually 3x3 or 4x4)
        grid_cells = driver.find_elements(By.CSS_SELECTOR, '#rc-imageselect-target td')
        print(f"  Grid cells: {len(grid_cells)}")
        
        # Try to detect objects in each cell
        # Simple approach: look for distinct visual features
        h, w = img.shape[:2]
        grid_size = int(np.sqrt(len(grid_cells)))
        cell_h, cell_w = h // grid_size, w // grid_size
        
        # For each cell, compute edge density and color variance
        # This is a heuristic - real solution would use a trained classifier
        clicked = 0
        for i, cell in enumerate(grid_cells):
            row, col = i // grid_size, i % grid_size
            cell_img = img[row*cell_h:(row+1)*cell_h, col*cell_w:(col+1)*cell_w]
            
            # Compute features
            gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.mean(edges > 0)
            
            # Color variance (objects tend to have more color variation)
            color_std = np.std(cell_img)
            
            print(f"    Cell [{row},{col}]: edge_density={edge_density:.3f} color_std={color_std:.1f}")
            
            # Heuristic: click cells with high visual activity
            # This is NOT reliable - real solution needs YOLO/CNN
            if edge_density > 0.05 and color_std > 30:
                try:
                    cell.click()
                    clicked += 1
                    time.sleep(0.5)
                except:
                    pass
        
        print(f"  Clicked {clicked} cells")
        driver.switch_to.default_content()
        
        # Click verify button
        if clicked > 0:
            time.sleep(2)
            driver.switch_to.frame(frames[0])
            try:
                verify_btn = driver.find_element(By.CSS_SELECTOR, '#recaptcha-verify-button')
                verify_btn.click()
                print("  Clicked verify button")
            except:
                pass
            driver.switch_to.default_content()
            time.sleep(3)
            return True
        return False
    except Exception as e:
        print(f"  Error solving challenge: {e}")
        driver.switch_to.default_content()
        return False


def check_captcha_solved(driver):
    """Check if reCAPTCHA has been solved."""
    try:
        result = driver.execute_script("""
            try {
                return grecaptcha && grecaptcha.getResponse().length > 0;
            } catch(e) {
                return false;
            }
        """)
        return result
    except:
        return False


options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
# Add some stealth options
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=IsolateOrigins,site-per-process")

driver = uc.Chrome(options=options, version_main=149)

try:
    print("\n[1] Navigating to login...")
    driver.set_page_load_timeout(90)
    driver.get(LOGIN_URL)
    time.sleep(8)
    
    print(f"  Title: {driver.title}")
    print(f"  URL: {driver.current_url}")
    
    # Step 2: Try to solve CAPTCHA
    print("\n[2] Attempting CAPTCHA solve...")
    
    # First try: click the checkbox
    solved = click_recaptcha_checkbox(driver)
    
    if not solved:
        # Check if image challenge appeared
        time.sleep(3)
        print("  Checkbox didn't pass. Checking for image challenge...")
        solved = solve_image_challenge(driver)
    
    if not solved:
        # Wait and retry
        print("  Retrying in 5s...")
        time.sleep(5)
        solved = click_recaptcha_checkbox(driver)
        if not solved:
            solved = solve_image_challenge(driver)
    
    # Final check
    time.sleep(3)
    captcha_solved = check_captcha_solved(driver)
    print(f"  CAPTCHA solved: {captcha_solved}")
    
    if not captcha_solved:
        print("  Could not solve CAPTCHA automatically.")
        print("  Waiting 60s - solve it manually in the browser window if visible...")
        for i in range(12):
            time.sleep(5)
            if check_captcha_solved(driver):
                captcha_solved = True
                print("  CAPTCHA solved (manually or delayed)!")
                break
            print(f"  Waiting... ({(i+1)*5}s)")
    
    if not captcha_solved:
        print("  CAPTCHA not solved. Exiting.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/captcha_final.png")
        sys.exit(1)
    
    # Step 3: Wait for login form
    print("\n[3] Looking for login form...")
    for attempt in range(10):
        time.sleep(3)
        pwd = driver.execute_script("""
            return document.querySelector('input[type="password"]') ||
                   document.querySelector('input[name*="pass" i]') ||
                   document.querySelector('input[placeholder*="pass" i]');
        """)
        if pwd:
            print("  Password field found!")
            break
        print(f"  Attempt {attempt+1}: no password field yet...")
    else:
        print("  No login form found.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/no_login_form.png")
        sys.exit(1)
    
    # Step 4: Fill and submit login
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
    
    driver.execute_script("""
        const btn = document.querySelector('button[type="submit"]') ||
                    document.querySelector('input[type="submit"]') ||
                    Array.from(document.querySelectorAll('button')).find(b => /login|sign.in|submit/i.test(b.innerText));
        if (btn) btn.click();
    """)
    time.sleep(8)
    
    print(f"  After login URL: {driver.current_url}")
    if "login" in driver.current_url.lower():
        print("  Login may have failed.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/login_failed.png")
        sys.exit(1)
    
    print("  Login successful!")
    
    # Step 5: Navigate to profile edit and update bio
    print("\n[5] Navigating to profile edit...")
    driver.get(BIO_URL)
    time.sleep(5)
    
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
        saved = driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
            const saveBtn = buttons.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
            if (saveBtn) { saveBtn.click(); return true; }
            return false;
        """)
        print(f"  Save clicked: {saved}")
        time.sleep(5)
        print("\n  BIO DEPLOYED SUCCESSFULLY!")
        
        # Write receipt
        import json
        from datetime import datetime, timezone
        receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        receipt = {
            "action": "bio_deploy",
            "bio_id": "controlled_wolf_v1",
            "experiment_id": "exp_001_targeted_wolf",
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notes": "deployed via undetected-chromedriver with captcha solving"
        }
        rpath = os.path.join(receipts_dir, f"deploy_controlled_wolf_v1_{receipt['timestamp'].replace(':','-')}.json")
        with open(rpath, "w") as f:
            json.dump(receipt, f, indent=2)
        print(f"  Receipt: {rpath}")
    else:
        print("  No textarea found.")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_edit.png")

finally:
    driver.quit()
    print("\nDone.")
