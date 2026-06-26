"""
RentMasseur Core — shared login, driver, availability, and bio update utilities.
Used by all 30 strategy scripts and the coordinator.
"""

import os
import re
import sys
import time
import json
import logging
import hashlib
import requests
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

RENTMASSEUR_USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
RENTMASSEUR_PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("grpw", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
LOGIN_URL = "https://rentmasseur.com/login"
AVAILABILITY_URL = "https://rentmasseur.com/settings?availability=1"
PROFILE_URL = "https://rentmasseur.com/settings?profile=1"
IMPLICIT_WAIT = 10
PAGE_TIMEOUT = 30

BIO_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bio_history.json")
BIOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bios")
os.makedirs(BIOS_DIR, exist_ok=True)


def setup_driver(headless: bool = True) -> webdriver.Chrome:
    if HAS_UC:
        opts = uc.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        try:
            import subprocess
            chrome_ver_out = subprocess.check_output(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"], stderr=subprocess.DEVNULL).decode().strip()
            chrome_major = int(re.search(r'(\d+)\.', chrome_ver_out).group(1))
            driver = uc.Chrome(options=opts, version_main=chrome_major)
        except Exception:
            driver = uc.Chrome(options=opts)
        driver.implicitly_wait(IMPLICIT_WAIT)
        driver.set_page_load_timeout(PAGE_TIMEOUT)
        return driver
    else:
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        driver = webdriver.Chrome(options=opts)
        driver.implicitly_wait(IMPLICIT_WAIT)
        driver.set_page_load_timeout(PAGE_TIMEOUT)
        return driver


def _dump_debug(driver: webdriver.Chrome, label: str) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    prefix = os.path.join(debug_dir, f"debug_{label}_{ts}")
    try:
        driver.save_screenshot(f"{prefix}.png")
    except Exception:
        pass
    try:
        with open(f"{prefix}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception:
        pass


def login(driver: webdriver.Chrome) -> bool:
    if not RENTMASSEUR_USERNAME or not RENTMASSEUR_PASSWORD:
        logger.error("Missing credentials")
        return False
    try:
        logger.info("Navigating to login: %s", LOGIN_URL)
        driver.set_page_load_timeout(90)
        driver.get(LOGIN_URL)
        time.sleep(8)
        for xpath in [
            "//button[contains(text(),'Accept')]",
            "//button[contains(text(),'OK')]",
            "//button[contains(text(),'Got it')]",
            "//button[contains(text(),'Dismiss')]",
            "//button[contains(text(),'Agree')]",
            "//button[contains(text(),'Continue')]",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].click();", el)
                time.sleep(1)
            except NoSuchElementException:
                pass

        for attempt in range(1, 5):
            logger.info("Login discovery attempt %d/5", attempt)
            time.sleep(3)
            result = driver.execute_script("""
                let pwd = document.querySelector('input[type=\"password\"]');
                if (!pwd) {
                    pwd = document.querySelector('input[name*=\"pass\" i]') ||
                          document.querySelector('input[id*=\"pass\" i]') ||
                          document.querySelector('input[placeholder*=\"pass\" i]') ||
                          document.querySelector('input[class*=\"pass\" i]');
                    if (pwd) { pwd.type = 'password'; }
                }
                if (!pwd) {
                    const allInputs = Array.from(document.querySelectorAll('input'));
                    for (const inp of allInputs) {
                        const ctx = (inp.name||'') + ' ' + (inp.id||'') + ' ' + (inp.placeholder||'') + ' ' + (inp.className||'');
                        if (/pass/i.test(ctx)) { pwd = inp; break; }
                    }
                }
                if (!pwd) return {error: 'no_password'};
                const allInputs = Array.from(document.querySelectorAll('input'));
                const candidates = allInputs.filter(i => i !== pwd && (i.type === 'text' || i.type === 'email'));
                let user = null, bestDist = Infinity;
                for (const cand of candidates) {
                    const pos = pwd.compareDocumentPosition(cand);
                    if (pos & Node.DOCUMENT_POSITION_PRECEDING) {
                        let dist = 0, el = cand;
                        while (el && el !== pwd) { el = el.nextElementSibling || el.parentElement; dist++; if (dist > 100) break; }
                        if (dist < bestDist) { bestDist = dist; user = cand; }
                    }
                }
                if (!user && candidates.length > 0) user = candidates[0];
                if (!user) return {error: 'no_username'};
                let btn = null;
                const form = pwd.closest('form');
                if (form) {
                    btn = form.querySelector('button[type=\"submit\"]') || form.querySelector('input[type=\"submit\"]');
                    if (!btn) { const fb = Array.from(form.querySelectorAll('button')); btn = fb.find(b => /login|sign.in|submit/i.test(b.innerText)) || fb[0]; }
                }
                if (!btn) {
                    let ancestor = pwd.parentElement;
                    for (let i = 0; i < 5 && ancestor && !btn; i++) {
                        const ab = Array.from(ancestor.querySelectorAll('button'));
                        btn = ab.find(b => /login|sign.in|submit/i.test(b.innerText)) || ab[0];
                        ancestor = ancestor.parentElement;
                    }
                }
                if (!btn) { const allBtns = Array.from(document.querySelectorAll('button, [role=\"button\"]')); btn = allBtns.find(b => /login|sign.in|submit/i.test(b.innerText)); }
                if (!btn) return {error: 'no_button'};
                function attrs(el) { return {tag: el.tagName.toLowerCase(), id: el.id||'', name: el.name||'', type: el.type||'', class: (el.className&&typeof el.className==='string')?el.className.split(' ').filter(Boolean).join(' '):'', placeholder: el.placeholder||''}; }
                return {user: attrs(user), pwd: attrs(pwd), btn: attrs(btn)};
            """)
            if isinstance(result, dict) and 'error' not in result:
                break
            logger.warning("Login attempt %d failed: %s", attempt, result.get('error'))
            if attempt < 5:
                time.sleep(5)
            else:
                logger.error("Login failed after 5 attempts")
                _dump_debug(driver, f"login_{result.get('error','unknown')}")
                return False

        def build_selector(info: dict) -> str:
            if info['id']: return f"#{info['id']}"
            if info['name']: return f"{info['tag']}[name='{info['name']}']"
            if info['placeholder']: return f"{info['tag']}[placeholder='{info['placeholder']}']"
            if info['class']: return f"{info['tag']}.{info['class'].split()[0]}"
            return info['tag']

        user_sel = build_selector(result['user'])
        pwd_sel = build_selector(result['pwd'])
        btn_sel = build_selector(result['btn'])
        # Use native setter for React/Next.js compatibility
        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, RENTMASSEUR_USERNAME, RENTMASSEUR_PASSWORD)
        time.sleep(1)
        # Submit via Enter key on password field
        try:
            pwd_el = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            pwd_el.send_keys(Keys.ENTER)
        except Exception:
            driver.execute_script("""
                const btn = document.querySelector('button[type="submit"]') ||
                            Array.from(document.querySelectorAll('button')).find(b => /login|sign|submit/i.test(b.innerText));
                if (btn) btn.click();
            """)
        time.sleep(5)
        if LOGIN_URL not in driver.current_url:
            logger.info("Login successful -> %s", driver.current_url)
            return True
        err = driver.execute_script("const el = document.querySelector('[role=alert], .error, .form-error'); return el ? el.innerText : '';")
        if err:
            logger.error("Login error: %s", err.strip())
        _dump_debug(driver, "login_failed")
        return False
    except Exception as e:
        logger.error("Login exception: %s", e)
        _dump_debug(driver, "login_exception")
        return False


def set_availability_24_7(driver: webdriver.Chrome) -> bool:
    try:
        logger.info("Setting availability: %s", AVAILABILITY_URL)
        driver.get(AVAILABILITY_URL)
        time.sleep(3)
        ok = driver.execute_script("""
            const selects = Array.from(document.querySelectorAll('select'));
            const buttons = Array.from(document.querySelectorAll('button'));
            const statusSelect = selects.find(s => {
                const opts = Array.from(s.options).map(o => o.text.toLowerCase());
                return opts.includes('available') || opts.includes('not set');
            });
            if (!statusSelect) return {error: 'no_status_select'};
            const availOpt = Array.from(statusSelect.options).find(
                o => o.text.toLowerCase().includes('available') && !o.text.toLowerCase().includes('not')
            );
            if (availOpt) { statusSelect.value = availOpt.value; statusSelect.dispatchEvent(new Event('change', {bubbles: true})); }
            const timeSelect = selects.find(s => {
                const opts = Array.from(s.options).map(o => o.text.toLowerCase());
                return opts.some(t => t.includes('hour') || t.includes('minute'));
            });
            if (timeSelect) {
                const durationOpts = Array.from(timeSelect.options).filter(o => /\\d/.test(o.text));
                if (durationOpts.length > 0) {
                    const longest = durationOpts[durationOpts.length - 1];
                    timeSelect.value = longest.value;
                    timeSelect.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }
            const setBtn = buttons.find(b => /set|save|apply/i.test(b.innerText));
            if (!setBtn) return {error: 'no_set_button'};
            setBtn.click();
            return {ok: true};
        """)
        if isinstance(ok, dict) and ok.get('error'):
            logger.error("Availability failed: %s", ok['error'])
            _dump_debug(driver, f"availability_{ok['error']}")
            return False
        logger.info("Availability set successfully")
        time.sleep(2)
        return True
    except Exception as e:
        logger.error("Availability exception: %s", e)
        return False


def _load_bio_history() -> list:
    if os.path.exists(BIO_HISTORY_FILE):
        try:
            with open(BIO_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_bio_history(history: list) -> None:
    try:
        with open(BIO_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-50:], f, indent=2)
    except Exception as e:
        logger.warning("Failed to save bio history: %s", e)


def _bio_hash(bio: str) -> str:
    return hashlib.md5(bio.strip().lower().encode()).hexdigest()[:12]


def groq_generate_bio(strategy_name: str, strategy_prompt: str, current_bio: Optional[str]) -> Optional[str]:
    if not GROQ_API_KEY:
        logger.error("No GROQ_API_KEY")
        return None
    history = _load_bio_history()
    used_hashes = {entry.get("hash", "") for entry in history}
    system_base = (
        "You are an elite copywriter for massage therapy profiles. "
        "Each bio must be under 300 words, magnetic, SEO-friendly, and conversion-optimized. "
        "Avoid explicit content. Include keywords: massage, therapeutic, deep tissue, relaxation, session, Manhattan. "
        "Always end with a subtle call-to-action."
    )
    context = f"\nCurrent bio:\n---\n{current_bio}\n---\n" if current_bio and current_bio.strip() else ""
    user_prompt = (
        f"{context}"
        f"Strategy: {strategy_name}\n"
        f"Instructions: {strategy_prompt}\n"
        f"Now write ONLY the bio text. No labels, no quotes, no explanation. Just the bio."
    )
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_base},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.9,
                "max_tokens": 600,
            },
            timeout=60,
        )
        resp.raise_for_status()
        bio = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
        h = _bio_hash(bio)
        if h in used_hashes:
            logger.info("Skipping duplicate bio strategy=%s", strategy_name)
            return None
        history.append({
            "timestamp": datetime.now().isoformat(),
            "strategy": strategy_name,
            "hash": h,
            "chars": len(bio),
            "bio_preview": bio[:120],
        })
        _save_bio_history(history)
        _save_bio_to_file(strategy_name, bio)
        logger.info("Generated bio: strategy=%s chars=%d", strategy_name, len(bio))
        return bio
    except Exception as e:
        logger.error("Groq API error for %s: %s", strategy_name, e)
        return None


def _save_bio_to_file(strategy_name: str, bio: str) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bio_{strategy_name}_{ts}.txt"
    filepath = os.path.join(BIOS_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(bio)
        logger.info("Bio saved to file: %s", filepath)
    except Exception as e:
        logger.warning("Failed to save bio to file: %s", e)


def update_bio(driver: webdriver.Chrome, new_bio: str) -> bool:
    try:
        urls_to_try = [
            "https://rentmasseur.com/settings/about",
            PROFILE_URL,
            "https://rentmasseur.com/settings?bio=1",
            "https://rentmasseur.com/settings",
            "https://rentmasseur.com/profile/edit",
            f"https://rentmasseur.com/{RENTMASSEUR_USERNAME}/edit",
        ]
        for url in urls_to_try:
            logger.info("Trying profile settings: %s", url)
            driver.get(url)
            time.sleep(3)
            result = driver.execute_script("""
                const textareas = Array.from(document.querySelectorAll('textarea'));
                const editables = Array.from(document.querySelectorAll('[contenteditable=\"true\"]'));
                const inputs = Array.from(document.querySelectorAll('input[type=\"text\"]'));
                function scoreBio(el, isTextarea) {
                    const clues = ['bio','about','description','profile','intro','summary'];
                    const text = (el.placeholder+' '+el.name+' '+(el.id||'')+' '+(el.getAttribute('aria-label')||'')).toLowerCase();
                    let score=0;
                    for (const c of clues) if (text.includes(c)) score+=3;
                    if (isTextarea) score+=5;
                    const val=el.value||el.innerText||'';
                    if (val.length>30) score+=2; if (val.length>100) score+=3;
                    return score;
                }
                let best=null, bestScore=-1;
                for (const el of textareas) { const s=scoreBio(el,true); if (s>bestScore){bestScore=s; best=el;} }
                for (const el of editables) { const s=scoreBio(el,false); if (s>bestScore){bestScore=s; best=el;} }
                if (!best && inputs.length>0) { for (const el of inputs){const s=scoreBio(el,false); if(s>bestScore){bestScore=s;best=el;}} }
                if (!best) return {error:'no_bio_field'};
                const current=best.value||best.innerText||'';
                return {
                    tag:best.tagName.toLowerCase(), id:best.id||'', name:best.name||'',
                    class:(best.className&&typeof best.className==='string')?best.className.split(' ').filter(Boolean).join(' '):'',
                    placeholder:best.placeholder||'', contenteditable:best.getAttribute('contenteditable')||'',
                    current:current.slice(0,500),
                    selector:best.tagName.toLowerCase()+(best.id?'#'+best.id:'')+(best.name?'[name=\"'+best.name+'\"]':''),
                };
            """)
            if isinstance(result, dict) and result.get('error'):
                logger.info("No bio field at %s, trying next...", url)
                continue
            logger.info("Found bio field: %s", result.get('selector'))
            current_bio = result.get('current', '')
            logger.info("Current bio preview: %s...", current_bio[:80])
            return result, current_bio
        logger.error("Bio field not found on any settings page")
        _dump_debug(driver, "bio_not_found")
        return None
    except Exception as e:
        logger.error("Bio update exception: %s", e)
        _dump_debug(driver, "bio_exception")
        return None


def save_bio_field(driver: webdriver.Chrome, result: dict, new_bio: str) -> bool:
    try:
        sel = result['selector']
        if result.get('contenteditable') == 'true':
            el = driver.find_element(By.CSS_SELECTOR, sel)
            driver.execute_script("arguments[0].innerText = arguments[1];", el, new_bio)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
        else:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            el.clear()
            el.send_keys(new_bio)
        save_ok = driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('button, input[type=\"submit\"], a[role=\"button\"]'));
            let saveBtn = buttons.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'')+' '+(b.value||'')+' '+(b.textContent||'')));
            if (!saveBtn) {
                const form = document.querySelector('textarea')?.closest('form');
                if (form) { const fb=Array.from(form.querySelectorAll('button, input[type=\"submit\"]')); saveBtn=fb.find(b=>/save|update|submit|apply|confirm/i.test((b.innerText||'')+' '+(b.value||''))); }
            }
            if (!saveBtn) return {error:'no_save_button'};
            saveBtn.click();
            return {ok:true};
        """)
        if isinstance(save_ok, dict) and save_ok.get('error'):
            logger.error("Save button not found: %s", save_ok['error'])
            _dump_debug(driver, "bio_no_save")
            return False
        logger.info("Bio updated and saved")
        time.sleep(2)
        return True
    except Exception as e:
        logger.error("Save bio exception: %s", e)
        return False
