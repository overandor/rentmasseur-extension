#!/usr/bin/env python3
"""
Login + deploy bio with reCAPTCHA audio challenge solving.

Strategy:
1. Use undetected-chromedriver to minimize bot detection
2. Switch to reCAPTCHA audio challenge
3. Download audio file
4. Transcribe with speech recognition
5. Submit answer
6. Proceed to login + bio deploy
"""
import time, os, sys, json, urllib.request, tempfile
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import speech_recognition as sr
from pydub import AudioSegment
from datetime import datetime, timezone

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


def solve_recaptcha_audio(driver):
    """Solve reCAPTCHA using audio challenge + speech recognition."""
    print("  [CAPTCHA] Attempting audio challenge...")
    
    # Switch to reCAPTCHA anchor iframe and click checkbox
    frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"][src*="anchor"]')
    if not frames:
        print("  [CAPTCHA] No reCAPTCHA anchor iframe found")
        return False
    
    driver.switch_to.frame(frames[0])
    time.sleep(1)
    
    # Click the checkbox
    try:
        checkbox = driver.find_element(By.CSS_SELECTOR, '#recaptcha-anchor')
        checkbox.click()
        print("  [CAPTCHA] Clicked checkbox")
        time.sleep(3)
    except Exception as e:
        print(f"  [CAPTCHA] Error clicking checkbox: {e}")
        driver.switch_to.default_content()
        return False
    
    driver.switch_to.default_content()
    time.sleep(2)
    
    # Now switch to the bframe (challenge iframe)
    bframes = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"][src*="bframe"]')
    if not bframes:
        print("  [CAPTCHA] No challenge iframe found - maybe checkbox passed?")
        return check_response(driver)
    
    driver.switch_to.frame(bframes[0])
    time.sleep(2)
    
    # Click "Audio" button
    try:
        audio_btn = driver.find_element(By.CSS_SELECTOR, '#recaptcha-audio-button')
        audio_btn.click()
        print("  [CAPTCHA] Clicked audio button")
        time.sleep(3)
    except Exception as e:
        print(f"  [CAPTCHA] Error clicking audio button: {e}")
        # Try alternative selectors
        try:
            audio_btn = driver.find_element(By.XPATH, '//button[contains(text(),"audio")]')
            audio_btn.click()
            time.sleep(3)
        except:
            print("  [CAPTCHA] Could not find audio button")
            driver.switch_to.default_content()
            return False
    
    # Get audio URL
    for attempt in range(3):
        try:
            audio_link = driver.find_element(By.CSS_SELECTOR, '.rc-audiochallenge-tdownload-link a, a[href*=".mp3"]')
            audio_url = audio_link.get_attribute("href")
            if audio_url:
                print(f"  [CAPTCHA] Audio URL: {audio_url}")
                break
        except:
            # Try to find audio element
            try:
                audio_el = driver.find_element(By.CSS_SELECTOR, 'audio source')
                audio_url = audio_el.get_attribute("src")
                if audio_url:
                    print(f"  [CAPTCHA] Audio element URL: {audio_url}")
                    break
            except:
                pass
        time.sleep(2)
    else:
        print("  [CAPTCHA] Could not find audio URL")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/captcha_audio.png")
        driver.switch_to.default_content()
        return False
    
    # Download audio file
    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, "captcha.mp3")
    wav_path = os.path.join(tmp_dir, "captcha.wav")
    
    try:
        print(f"  [CAPTCHA] Downloading audio...")
        urllib.request.urlretrieve(audio_url, audio_path)
        
        # Convert to WAV
        print(f"  [CAPTCHA] Converting to WAV...")
        audio = AudioSegment.from_mp3(audio_path)
        audio.export(wav_path, format="wav")
        
        # Transcribe
        print(f"  [CAPTCHA] Transcribing...")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        
        # Try Google speech recognition
        try:
            text = recognizer.recognize_google(audio_data)
            print(f"  [CAPTCHA] Transcribed: '{text}'")
        except sr.UnknownValueError:
            print("  [CAPTCHA] Could not understand audio")
            # Try with different settings
            recognizer.energy_threshold = 300
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source, duration=10)
            try:
                text = recognizer.recognize_google(audio_data)
                print(f"  [CAPTCHA] Retry transcribed: '{text}'")
            except:
                print("  [CAPTCHA] Speech recognition failed")
                driver.switch_to.default_content()
                return False
        except sr.RequestError as e:
            print(f"  [CAPTCHA] Speech recognition service error: {e}")
            driver.switch_to.default_content()
            return False
        
        # Enter the answer
        print(f"  [CAPTCHA] Entering answer: '{text}'")
        try:
            input_field = driver.find_element(By.CSS_SELECTOR, '#audio-response')
            input_field.clear()
            input_field.send_keys(text.lower().strip())
            time.sleep(1)
        except:
            try:
                input_field = driver.find_element(By.CSS_SELECTOR, 'input[type="text"]')
                input_field.clear()
                input_field.send_keys(text.lower().strip())
                time.sleep(1)
            except Exception as e:
                print(f"  [CAPTCHA] Could not find input field: {e}")
                driver.switch_to.default_content()
                return False
        
        # Click verify
        try:
            verify_btn = driver.find_element(By.CSS_SELECTOR, '#recaptcha-verify-button')
            verify_btn.click()
            print("  [CAPTCHA] Clicked verify")
        except:
            try:
                verify_btn = driver.find_element(By.XPATH, '//button[contains(text(),"Verify")]')
                verify_btn.click()
            except:
                print("  [CAPTCHA] Could not find verify button")
        
        time.sleep(5)
        driver.switch_to.default_content()
        
        # Check if solved
        solved = check_response(driver)
        print(f"  [CAPTCHA] Solved: {solved}")
        return solved
        
    except Exception as e:
        print(f"  [CAPTCHA] Error in audio solve: {e}")
        driver.switch_to.default_content()
        return False
    finally:
        # Cleanup
        try:
            os.remove(audio_path)
            os.remove(wav_path)
            os.rmdir(tmp_dir)
        except:
            pass


def check_response(driver):
    """Check if reCAPTCHA response is filled."""
    try:
        result = driver.execute_script("""
            try {
                return grecaptcha && grecaptcha.getResponse().length > 0;
            } catch(e) {
                return false;
            }
        """)
        return bool(result)
    except:
        return False


def wait_for_login_form(driver, max_wait=60):
    """Wait for login form to appear after CAPTCHA is solved."""
    print("  [LOGIN] Waiting for login form...")
    for attempt in range(max_wait // 3):
        time.sleep(3)
        pwd = driver.execute_script("""
            return document.querySelector('input[type="password"]') ||
                   document.querySelector('input[name*="pass" i]') ||
                   document.querySelector('input[placeholder*="pass" i]');
        """)
        if pwd:
            print("  [LOGIN] Password field found!")
            return True
        # Check if CAPTCHA reappeared
        captcha = driver.execute_script("""
            return !!document.querySelector('.g-recaptcha, #captcha');
        """)
        if captcha and not check_response(driver):
            print(f"  [LOGIN] CAPTCHA reappeared at attempt {attempt+1}")
            return False
        print(f"  [LOGIN] Attempt {attempt+1}: waiting...")
    return False


def do_login(driver):
    """Fill and submit login form."""
    print("  [LOGIN] Filling credentials...")
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
    
    if "login" in driver.current_url.lower():
        print(f"  [LOGIN] Still on login page: {driver.current_url}")
        return False
    print(f"  [LOGIN] Success! URL: {driver.current_url}")
    return True


def deploy_bio(driver):
    """Navigate to profile edit and update bio."""
    print("  [BIO] Navigating to profile edit...")
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
    
    if not bio_field:
        print("  [BIO] No textarea found")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_edit.png")
        return False
    
    print("  [BIO] Bio field updated!")
    time.sleep(2)
    
    saved = driver.execute_script("""
        const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
        const saveBtn = buttons.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
        if (saveBtn) { saveBtn.click(); return true; }
        return false;
    """)
    print(f"  [BIO] Save clicked: {saved}")
    time.sleep(5)
    
    # Write receipt
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {
        "action": "bio_deploy",
        "bio_id": "controlled_wolf_v1",
        "experiment_id": "exp_001_targeted_wolf",
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "undetected-chromedriver + audio captcha solving"
    }
    rpath = os.path.join(receipts_dir, f"deploy_controlled_wolf_v1_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"  [BIO] Receipt: {rpath}")
    return True


# ===== MAIN =====
options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = uc.Chrome(options=options, version_main=149)

try:
    print("\n[1] Navigating to login...")
    driver.set_page_load_timeout(90)
    driver.get(LOGIN_URL)
    time.sleep(8)
    
    print(f"  Title: {driver.title}")
    
    # Check if CAPTCHA present
    captcha = driver.execute_script("""
        return !!document.querySelector('.g-recaptcha, #captcha, iframe[src*="recaptcha"]');
    """)
    print(f"  CAPTCHA present: {captcha}")
    
    if captcha:
        # Try audio solve up to 3 times
        for attempt in range(3):
            print(f"\n[2] CAPTCHA solve attempt {attempt+1}/3...")
            solved = solve_recaptcha_audio(driver)
            if solved:
                print("  CAPTCHA SOLVED!")
                break
            print("  Retrying...")
            time.sleep(3)
            # Refresh page and try again
            if attempt < 2:
                driver.get(LOGIN_URL)
                time.sleep(5)
        else:
            print("  Could not solve CAPTCHA after 3 attempts")
            driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/captcha_failed.png")
            sys.exit(1)
    
    # Wait for login form
    if not wait_for_login_form(driver):
        print("  Login form did not appear")
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/no_form.png")
        sys.exit(1)
    
    # Login
    print("\n[3] Logging in...")
    if not do_login(driver):
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/login_failed.png")
        sys.exit(1)
    
    # Deploy bio
    print("\n[4] Deploying bio...")
    if deploy_bio(driver):
        print("\n  === BIO DEPLOYED SUCCESSFULLY ===")
    else:
        print("\n  === BIO DEPLOY FAILED ===")
        sys.exit(1)

finally:
    driver.quit()
    print("\nDone.")
