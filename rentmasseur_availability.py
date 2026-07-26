#!/usr/bin/env python3
"""
Selenium automation script to keep rentmasseur.com availability set to 24/7.
Credentials are loaded from a .env file or environment variables.
"""

import argparse
import json
import os
import re
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

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
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException,
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Load .env file if present (project root or current directory)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

# Configuration from environment
RENTMASSEUR_USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
RENTMASSEUR_PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
PROXY_URL = os.getenv("PROXY_URL", "")
AVAILABILITY_URL = "https://rentmasseur.com/settings?availability=1"
LOGIN_URL = "https://rentmasseur.com/login"

# Timing settings
IMPLICIT_WAIT = 10
PAGE_TIMEOUT = 30
CHECK_INTERVAL_MINUTES = 5


def _proxy_arg(proxy_url: str) -> str:
    """Return a Chrome --proxy-server argument for http/socks5 proxies."""
    p = proxy_url.strip()
    if p.startswith(("http://", "https://", "socks5://", "socks4://")):
        return f"--proxy-server={p}"
    return f"--proxy-server=http://{p}"


def setup_driver(headless: bool = True) -> webdriver.Chrome:
    """Configure and return a Chrome WebDriver instance with stealth options."""
    if HAS_UC:
        chrome_options = uc.ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        if PROXY_URL:
            logger.info("Using proxy for Chrome: %s", PROXY_URL)
            chrome_options.add_argument(_proxy_arg(PROXY_URL))
        try:
            import subprocess, re
            chrome_ver_out = subprocess.check_output(["google-chrome", "--version"], stderr=subprocess.DEVNULL).decode().strip()
            chrome_major = int(re.search(r'(\d+)\.', chrome_ver_out).group(1))
            driver = uc.Chrome(options=chrome_options, version_main=chrome_major)
        except Exception:
            driver = uc.Chrome(options=chrome_options)
        driver.implicitly_wait(IMPLICIT_WAIT)
        driver.set_page_load_timeout(PAGE_TIMEOUT)
        return driver
    else:
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        if PROXY_URL:
            logger.info("Using proxy for Chrome: %s", PROXY_URL)
            chrome_options.add_argument(_proxy_arg(PROXY_URL))
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.implicitly_wait(IMPLICIT_WAIT)
        driver.set_page_load_timeout(PAGE_TIMEOUT)
        return driver


POPUP_DISMISS_SELECTORS = [
    # Cookie / GDPR consent
    "button[id*='cookie']",
    "button[class*='cookie']",
    "button[aria-label*='cookie']",
    "button[aria-label*='Cookie']",
    "button[aria-label*='Accept']",
    "button[aria-label*='accept']",
    "button[data-testid*='cookie']",
    "button[data-testid*='close']",
    "a[href*='cookie']",
    "[class*='cookie-banner'] button",
    "[class*='cookieConsent'] button",
    "[class*='gdpr'] button",
    "[class*='consent'] button",
    "[id*='onetrust'] button",
    "[id*='CybotCookiebotDialogBodyButton']",
    "[class*='banner'] button[aria-label*='close']",
    "[class*='modal'] button[aria-label*='close']",
    "[class*='dialog'] button[aria-label*='close']",
    "[role='dialog'] button",
    "[role='alert'] button",
    # Text-based common buttons
    "//button[contains(text(),'Accept')]",
    "//button[contains(text(),'OK')]",
    "//button[contains(text(),'Got it')]",
    "//button[contains(text(),'Dismiss')]",
    "//button[contains(text(),'Agree')]",
    "//button[contains(text(),'Continue')]",
    "//button[contains(text(),'I understand')]",
    "//button[contains(text(),'Allow')]",
    "//button[contains(text(),'Enable')]",
    "//button[contains(text(),'Maybe later')]",
    "//button[contains(text(),'Not now')]",
    "//button[contains(text(),'Close')]",
    "//button[contains(text(),'×')]",
    "//a[contains(text(),'Accept')]",
    "//a[contains(text(),'Dismiss')]",
]


def dismiss_popups(driver: webdriver.Chrome) -> None:
    """Dismiss cookie banners, GDPR dialogs, and other popups that block interaction."""
    clicked = 0
    # Try CSS selectors first via JS (fastest)
    for selector in POPUP_DISMISS_SELECTORS:
        if not selector.startswith("//"):
            try:
                elements = driver.execute_script(
                    "return Array.from(document.querySelectorAll(arguments[0])).filter(el => el.offsetParent !== null);",
                    selector,
                )
                for el in elements:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", el)
                        clicked += 1
                        time.sleep(0.3)
                    except Exception:
                        pass
            except Exception:
                pass
    # Try XPath selectors
    for xpath in POPUP_DISMISS_SELECTORS:
        if xpath.startswith("//"):
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    try:
                        if el.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", el)
                            clicked += 1
                            time.sleep(0.3)
                    except Exception:
                        pass
            except Exception:
                pass
    # Generic overlay / modal close via JS: try to click anything with 'close' or 'dismiss' aria-label
    try:
        driver.execute_script("""
            const closeBtns = Array.from(document.querySelectorAll('button, a, [role="button"]'))
                .filter(b => b.offsetParent !== null &&
                    (/close|dismiss|reject|deny|skip|cancel/i.test((b.getAttribute('aria-label')||'') + ' ' + (b.innerText||''))));
            closeBtns.forEach(b => { try { b.click(); } catch(e) {} });
        """)
    except Exception:
        pass
    if clicked:
        logger.info("Dismissed %d popup/banner elements", clicked)


def _find_element(driver, by, value, timeout=5):
    """Helper to find an element with a short timeout."""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        return None


def scan_page(driver: webdriver.Chrome) -> None:
    """Brute-force scan: dump every interactive element with its selector hash."""
    logger.info("=== DOM SCAN START ===")
    elements = driver.execute_script("""
        const data = [];
        const inputs = document.querySelectorAll('input, textarea, select');
        const buttons = document.querySelectorAll('button, [role="button"]');
        
        function shortId(el) {
            const id = el.id ? '#' + el.id : '';
            const cls = (el.className && typeof el.className === 'string')
                ? '.' + el.className.split(' ').filter(Boolean).join('.')
                : '';
            const name = el.name ? '[name=' + el.name + ']' : '';
            const type = el.type ? '[type=' + el.type + ']' : '';
            return el.tagName.toLowerCase() + id + name + type;
        }
        
        function xpath(el) {
            const idx = (s, n) => {
                let c = 1;
                for (const p of n.parentNode.children) {
                    if (p === n) return c;
                    if (p.nodeName === n.nodeName) c++;
                }
                return 1;
            };
            let p = el, path = '';
            while (p && p.nodeType === 1) {
                const name = p.nodeName.toLowerCase();
                const i = idx(name, p);
                path = '/' + name + '[' + i + ']' + path;
                p = p.parentNode;
            }
            return path;
        }
        
        for (const el of inputs) {
            data.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                selector: shortId(el),
                xpath: xpath(el),
                text: (el.value || el.textContent || '').slice(0, 50),
            });
        }
        for (const el of buttons) {
            data.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                selector: shortId(el),
                xpath: xpath(el),
                text: (el.textContent || el.innerText || '').trim().slice(0, 50),
            });
        }
        return data;
    """)
    for el in elements:
        logger.info("SCAN | %-12s | %-20s | xpath=%s", el['selector'], el['text'][:20], el['xpath'])
    logger.info("=== DOM SCAN END (%d elements) ===", len(elements))


def _is_captcha_page(driver: webdriver.Chrome) -> bool:
    """Check if the current page is a CrowdSec captcha or anti-bot challenge."""
    try:
        page_text = driver.execute_script("return document.body ? document.body.innerText.slice(0, 2000) : '';") or ""
        page_src = driver.execute_script("return document.documentElement ? document.documentElement.outerHTML.slice(0, 3000) : '';") or ""
        indicators = [
            "crowdsec", "captcha", "checking your browser", "please wait",
            "ddos protection", "access denied", "are you human", "verify you are",
            "challenge", "cloudflare", "just a moment", "enable javascript",
            "access forbidden", "unable to visit", "security check",
        ]
        text_lower = page_text.lower() + page_src.lower()
        return any(ind in text_lower for ind in indicators)
    except Exception:
        return False


def brute_force_login(driver: webdriver.Chrome, max_retries: int = 5) -> bool:
    """Log in using brute-force DOM discovery via JavaScript with retry logic."""
    if not RENTMASSEUR_USERNAME or not RENTMASSEUR_PASSWORD:
        logger.error("Missing credentials")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Login attempt %d/%d — navigating to %s", attempt, max_retries, LOGIN_URL)
            driver.set_page_load_timeout(90)
            driver.get(LOGIN_URL)

            # Wait for SPA hydration with increasing delays
            wait_time = 5 + (attempt * 3)
            logger.info("Waiting %ds for page to render...", wait_time)
            time.sleep(wait_time)

            # Check for captcha / anti-bot page
            if _is_captcha_page(driver):
                logger.warning("Captcha/anti-bot page detected on attempt %d — refreshing", attempt)
                if attempt < max_retries:
                    time.sleep(10)
                    driver.refresh()
                    time.sleep(10)
                    continue
                else:
                    logger.error("Captcha blocking login after %d attempts", max_retries)
                    _dump_debug(driver, "login_captcha_final")
                    return False

            # Dismiss cookie/GPS banners and other popups
            dismiss_popups(driver)
            time.sleep(2)

            # Wait for password field to appear (SPA may still be hydrating)
            pwd_field = _find_element(driver, By.CSS_SELECTOR, 'input[type="password"]', timeout=15)
            if not pwd_field:
                logger.warning("No password field found on attempt %d — page may still be loading", attempt)
                # Check if page has any inputs at all
                input_count = driver.execute_script("return document.querySelectorAll('input').length;") or 0
                logger.info("Page has %d input elements", input_count)
                if input_count == 0:
                    logger.warning("Page has 0 inputs — likely blocked or not rendered")
                    _dump_debug(driver, f"login_no_inputs_attempt{attempt}")
                    if attempt < max_retries:
                        time.sleep(15)
                        continue
                else:
                    _dump_debug(driver, f"login_no_password_attempt{attempt}")
                    if attempt < max_retries:
                        time.sleep(10)
                        continue

            # Brute-force: ask the browser to find login fields for us
            result = driver.execute_script("""
                const pwd = document.querySelector('input[type=\"password\"]');
                if (!pwd) return {error: 'no_password'};
                
                // Scan ALL inputs on the page, then find text/email ones that precede the password
                const allInputs = Array.from(document.querySelectorAll('input'));
                const candidates = allInputs.filter(i => 
                    i !== pwd && (i.type === 'text' || i.type === 'email' || i.type === 'tel')
                );
                
                // Prefer the candidate that is closest (preceding) in DOM order
                let user = null;
                let bestDist = Infinity;
                for (const cand of candidates) {
                    const pos = pwd.compareDocumentPosition(cand);
                    if (pos & Node.DOCUMENT_POSITION_PRECEDING) {
                        // Heuristic: measure "distance" by counting elements between them
                        let dist = 0;
                        let el = cand;
                        while (el && el !== pwd) {
                            el = el.nextElementSibling || el.parentElement;
                            dist++;
                            if (dist > 100) break;
                        }
                        if (dist < bestDist) {
                            bestDist = dist;
                            user = cand;
                        }
                    }
                }
                if (!user && candidates.length > 0) user = candidates[0];
                if (!user) return {error: 'no_username'};
                
                // Find submit button: search form first, then ancestor chain, then whole doc
                let btn = null;
                const form = pwd.closest('form');
                if (form) {
                    btn = form.querySelector('button[type=\"submit\"]') || form.querySelector('input[type=\"submit\"]');
                    if (!btn) {
                        const fb = Array.from(form.querySelectorAll('button'));
                        btn = fb.find(b => /login|sign.in|submit/i.test(b.innerText)) || fb[0];
                    }
                }
                if (!btn) {
                    // Walk up ancestors looking for a button
                    let ancestor = pwd.parentElement;
                    for (let i = 0; i < 5 && ancestor && !btn; i++) {
                        const ab = Array.from(ancestor.querySelectorAll('button'));
                        btn = ab.find(b => /login|sign.in|submit/i.test(b.innerText)) || ab[0];
                        ancestor = ancestor.parentElement;
                    }
                }
                if (!btn) {
                    // Last resort: any button on page that looks like login
                    const allBtns = Array.from(document.querySelectorAll('button, [role=\"button\"]'));
                    btn = allBtns.find(b => /login|sign.in|submit/i.test(b.innerText));
                }
                if (!btn) return {error: 'no_button'};
                
                // Return identifying attributes so Selenium can locate them
                function attrs(el) {
                    const id = el.id ? '#' + el.id : '';
                    const cls = (el.className && typeof el.className === 'string')
                        ? '.' + el.className.split(' ').filter(Boolean).join('.')
                        : '';
                    const name = el.name ? '[name=' + el.name + ']' : '';
                    const type = el.type ? '[type=' + el.type + ']' : '';
                    return {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        name: el.name || '',
                        type: el.type || '',
                        class: (el.className && typeof el.className === 'string') 
                            ? el.className.split(' ').filter(Boolean).join(' ') 
                            : '',
                        placeholder: el.placeholder || '',
                        selector: el.tagName.toLowerCase() + id + name + type + cls.split('.')[0],
                    };
                }
                return {
                    user: attrs(user),
                    pwd: attrs(pwd),
                    btn: attrs(btn),
                };
            """)
            
            if isinstance(result, dict) and 'error' in result:
                logger.warning("Login discovery failed on attempt %d: %s", attempt, result['error'])
                scan_page(driver)
                _dump_debug(driver, f"login_brute_force_{result['error']}_attempt{attempt}")
                if attempt < max_retries:
                    time.sleep(10)
                    continue
                return False
            
            logger.info("Discovered login form: user=%s, pwd=%s, btn=%s", 
                        result['user']['selector'], result['pwd']['selector'], result['btn']['selector'])
            
            # Build Selenium selectors from discovered attributes
            def build_selector(info: dict) -> str:
                tag = info['tag']
                if info['id']: return f"#{info['id']}"
                if info['name']: return f"{tag}[name='{info['name']}']"
                if info['placeholder']: return f"{tag}[placeholder='{info['placeholder']}']"
                if info['class']: return f"{tag}.{info['class'].split()[0]}"
                return tag
            
            user_sel = build_selector(result['user'])
            pwd_sel  = build_selector(result['pwd'])
            btn_sel  = build_selector(result['btn'])
            
            username_field = driver.find_element(By.CSS_SELECTOR, user_sel)
            password_field = driver.find_element(By.CSS_SELECTOR, pwd_sel)
            submit_btn     = driver.find_element(By.CSS_SELECTOR, btn_sel)
            
            username_field.clear()
            username_field.send_keys(RENTMASSEUR_USERNAME)
            password_field.clear()
            password_field.send_keys(RENTMASSEUR_PASSWORD)
            logger.info("Filled credentials into %s / %s", user_sel, pwd_sel)
            
            driver.execute_script("arguments[0].click();", submit_btn)
            logger.info("Clicked submit: %s", btn_sel)
            time.sleep(5)
            
            # Verify login success
            dismiss_popups(driver)
            current_url = driver.current_url
            if LOGIN_URL not in current_url:
                logger.info("Login successful (redirected to %s)", current_url)
                return True
            
            # Check for error messages
            error_text = driver.execute_script("""
                const el = document.querySelector('[role=alert], .error, .form-error, .notification');
                return el ? el.innerText : '';
            """)
            if error_text:
                logger.error("Login page shows error: %s", error_text.strip())
            
            logger.warning("Still on login page after submit (attempt %d)", attempt)
            scan_page(driver)
            _dump_debug(driver, f"login_still_on_page_attempt{attempt}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            
        except TimeoutException:
            logger.warning("Login page load timed out on attempt %d", attempt)
            _dump_debug(driver, f"login_timeout_attempt{attempt}")
            if attempt < max_retries:
                time.sleep(15)
                continue
        except WebDriverException as e:
            logger.warning("WebDriver error on attempt %d: %s", attempt, e)
            _dump_debug(driver, f"login_webdriver_error_attempt{attempt}")
            if attempt < max_retries:
                time.sleep(15)
                continue
        except Exception as e:
            logger.warning("Unexpected error on attempt %d: %s", attempt, e)
            if attempt < max_retries:
                time.sleep(15)
                continue
    
    logger.error("Login failed after %d attempts", max_retries)
    return False


def login(driver: webdriver.Chrome) -> bool:
    """Login using native input setter + Enter key (works with Next.js/React SPAs)."""
    if not RENTMASSEUR_USERNAME or not RENTMASSEUR_PASSWORD:
        logger.error("Missing credentials")
        return False

    for attempt in range(1, 4):
        logger.info("Login attempt %d/3 — navigating to %s", attempt, LOGIN_URL)
        driver.set_page_load_timeout(90)
        driver.get(LOGIN_URL)
        time.sleep(6)

        # Check for CAPTCHA
        captcha = driver.execute_script("""
            return !!document.querySelector('.g-recaptcha, #captcha, iframe[src*="recaptcha"]');
        """)
        if captcha:
            logger.warning("CAPTCHA detected on attempt %d — waiting", attempt)
            time.sleep(10)
            captcha = driver.execute_script("""
                return !!document.querySelector('.g-recaptcha, #captcha, iframe[src*="recaptcha"]');
            """)
            if captcha:
                logger.error("CAPTCHA still present after wait")
                _dump_debug(driver, f"login_captcha_attempt{attempt}")
                if attempt < 3:
                    time.sleep(10)
                    continue
                return False

        # Dismiss popups
        dismiss_popups(driver)
        time.sleep(2)

        # Fill login form using native setter
        result = driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            if (!pwd) return {error: 'no_password'};
            if (!user) return {error: 'no_username'};
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            ns.call(user, arguments[0]);
            user.dispatchEvent(new Event('input', {bubbles: true}));
            ns.call(pwd, arguments[1]);
            pwd.dispatchEvent(new Event('input', {bubbles: true}));
            return {ok: true, user_id: user.id, pwd_id: pwd.id};
        """, RENTMASSEUR_USERNAME, RENTMASSEUR_PASSWORD)

        if isinstance(result, dict) and 'error' in result:
            logger.warning("Login form error on attempt %d: %s", attempt, result['error'])
            _dump_debug(driver, f"login_{result['error']}_attempt{attempt}")
            if attempt < 3:
                time.sleep(10)
                continue
            return False

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
            logger.info("Login successful (redirected to %s)", driver.current_url)
            return True

        logger.warning("Still on login page after submit (attempt %d)", attempt)
        _dump_debug(driver, f"login_still_on_page_attempt{attempt}")
        if attempt < 3:
            time.sleep(10)
            continue

    logger.error("Login failed after 3 attempts")
    return False


def _dump_debug(driver: webdriver.Chrome, label: str) -> None:
    """Save screenshot and page source for debugging."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    prefix = os.path.join(debug_dir, f"debug_{label}_{ts}")
    try:
        driver.save_screenshot(f"{prefix}.png")
        logger.info("Screenshot saved: %s.png", prefix)
    except Exception as e:
        logger.error("Failed to save screenshot: %s", e)
    try:
        with open(f"{prefix}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Page source saved: %s.html", prefix)
    except Exception as e:
        logger.error("Failed to save page source: %s", e)


def scrape_profile_metrics(driver: webdriver.Chrome) -> dict:
    """Scrape visitor metrics from /settings/whosawme while already logged in.

    Uses a fast requests GET with Selenium cookies rather than driver.get,
    because the RM SPA can hang Selenium page loads past their timeouts.
    """
    metrics = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "requests_whosawme",
        "profile_views": 0,
        "unique_visitors": 0,
        "repeat_visitors": 0,
    }
    try:
        logger.info("Fetching visitor metrics via requests: https://rentmasseur.com/settings/whosawme")
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        resp = requests.get(
            "https://rentmasseur.com/settings/whosawme",
            cookies=cookies,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=20,
        )
        resp.raise_for_status()
        html = resp.text

        # Visitor profile links are typically /{username}
        seen = set()
        visitors = []
        for href in re.findall(r'href=["\'](https://rentmasseur\.com/[^"\']+)["\']', html):
            path = href.split("rentmasseur.com/", 1)[1]
            if path in ("", "settings", "whosawme") or path.startswith(("settings/", "about/", "login")):
                continue
            user = path.split("/")[0]
            if user and user not in seen and len(user) > 2:
                seen.add(user)
                visitors.append(user)

        # Also look for relative links
        for href in re.findall(r'href=["\'](/[^"\']+)["\']', html):
            user = href.strip("/").split("/")[0]
            if user in ("", "settings", "whosawme") or user.startswith(("settings/", "about/", "login")):
                continue
            if user and user not in seen and len(user) > 2:
                seen.add(user)
                visitors.append(user)

        metrics["profile_views"] = len(visitors)
        metrics["unique_visitors"] = len(visitors)
        logger.info("Scraped %d visitor(s) from Who Saw Me", len(visitors))

        # Persist to metrics pipeline files
        content_dir = Path("content")
        content_dir.mkdir(exist_ok=True)
        ingest_path = content_dir / "metrics_ingest.jsonl"
        with open(ingest_path, "a") as f:
            f.write(json.dumps(metrics) + "\n")
        live_path = content_dir / "live_metrics.json"
        with open(live_path, "w") as f:
            json.dump(metrics, f, indent=2)
        logger.info("Wrote metrics to %s and %s", ingest_path, live_path)
    except Exception as e:
        logger.error("Failed to scrape profile metrics: %s", e)
    return metrics


def set_availability_24_7(driver: webdriver.Chrome) -> bool:
    """Navigate to availability settings and enable 24/7 availability."""
    try:
        logger.info("Navigating to availability settings: %s", AVAILABILITY_URL)
        driver.set_page_load_timeout(90)
        driver.get(AVAILABILITY_URL)

        # Wait for SPA to render — use increasing delays with retry
        for wait_round in range(1, 5):
            time.sleep(10 + (wait_round * 5))  # 15s, 20s, 25s, 30s
            logger.info("Availability page wait round %d — checking for controls...", wait_round)

            # Dismiss any popups that could block the availability controls
            dismiss_popups(driver)

            # Check if selects OR custom dropdowns have rendered
            select_count = driver.execute_script("return document.querySelectorAll('select').length;") or 0
            button_count = driver.execute_script("return document.querySelectorAll('button').length;") or 0
            dropdown_count = driver.execute_script("return document.querySelectorAll('[class*=\"dropdown\"], [class*=\"select\"], [role=\"listbox\"], [role=\"combobox\"]').length;") or 0
            link_count = driver.execute_script("return document.querySelectorAll('a').length;") or 0
            logger.info("Page has %d selects, %d buttons, %d dropdowns, %d links", select_count, button_count, dropdown_count, link_count)

            if select_count > 0 or dropdown_count > 0:
                break

            if wait_round < 4:
                logger.warning("No selects/dropdowns found yet — waiting longer for SPA to render")
                _dump_debug(driver, f"availability_no_selects_round{wait_round}")

        # Do everything in JS since the two selects share identical classes
        ok = driver.execute_script("""
            const selects = Array.from(document.querySelectorAll('select'));
            const buttons = Array.from(document.querySelectorAll('button'));
            const allText = document.body ? document.body.innerText.slice(0, 3000) : '';
            
            // Find availability status select (options contain 'Available' / 'Not Set')
            const statusSelect = selects.find(s => {
                const opts = Array.from(s.options).map(o => o.text.toLowerCase());
                return opts.includes('available') || opts.includes('not set');
            });
            if (!statusSelect) return {error: 'no_status_select', select_count: selects.length, button_count: buttons.length, page_text: allText};
            
            // Select 'Available' (skip 'Not Available')
            const availOpt = Array.from(statusSelect.options).find(
                o => o.text.toLowerCase().includes('available') && !o.text.toLowerCase().includes('not')
            );
            if (availOpt) {
                statusSelect.value = availOpt.value;
                statusSelect.dispatchEvent(new Event('change', {bubbles: true}));
            }
            
            // Find time select (options contain 'Hour' or 'Minutes')
            const timeSelect = selects.find(s => {
                const opts = Array.from(s.options).map(o => o.text.toLowerCase());
                return opts.some(t => t.includes('hour') || t.includes('minute'));
            });
            if (timeSelect) {
                // Pick the longest duration (last option that contains a number)
                const durationOpts = Array.from(timeSelect.options).filter(
                    o => /\\d/.test(o.text)
                );
                if (durationOpts.length > 0) {
                    const longest = durationOpts[durationOpts.length - 1];
                    timeSelect.value = longest.value;
                    timeSelect.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }
            
            // Find and click SET button
            const setBtn = buttons.find(b => /set|save|apply/i.test(b.innerText));
            if (!setBtn) return {error: 'no_set_button', button_texts: buttons.map(b => b.innerText.slice(0, 30))};
            setBtn.click();
            
            return {ok: true};
        """)
        
        if isinstance(ok, dict) and ok.get('error'):
            logger.error("Availability JS automation failed: %s", ok)
            scan_page(driver)
            _dump_debug(driver, f"availability_{ok['error']}")
            return False
        
        logger.info("Availability set via JS automation")
        time.sleep(3)
        return True
        
    except TimeoutException:
        logger.error("Availability page timed out")
        _dump_debug(driver, "availability_timeout")
        return False
    except WebDriverException as e:
        logger.error("WebDriver error setting availability: %s", e)
        return False


def run_once(headless: bool = True) -> bool:
    """Execute a single availability check-and-set cycle."""
    driver: Optional[webdriver.Chrome] = None
    try:
        driver = setup_driver(headless=headless)
        # Try brute_force_login first (more robust for SPAs), fall back to login()
        if not brute_force_login(driver, max_retries=3):
            logger.warning("Brute-force login failed, trying alternate login method")
            if not login(driver):
                _write_availability_json(False, "login_failed")
                return False
        success = set_availability_24_7(driver)
        _write_availability_json(success, "set_24_7" if success else "set_failed")
        if success:
            scrape_profile_metrics(driver)
        return success
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        _write_availability_json(False, f"exception: {e}")
        return False
    finally:
        if driver:
            driver.quit()


def _write_availability_json(success: bool, reason: str) -> None:
    """Write availability.json so the workflow can commit it."""
    import json
    data = {
        "availability_enforced": success,
        "automated_login": True,
        "availability_updated": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "availability.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Wrote availability.json: %s", json.dumps(data))
    except Exception as e:
        logger.error("Failed to write availability.json: %s", e)


def main() -> None:
    """Run the availability keeper in a loop or once for CI/CD."""
    parser = argparse.ArgumentParser(description="Keep RentMasseur availability set to 24/7")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit (for CI/CD)")
    parser.add_argument("--headless", default="true", help="Run headless (true/false)")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL_MINUTES, help="Loop interval in minutes")
    args = parser.parse_args()

    headless = args.headless.lower() != "false"

    if args.once:
        logger.info("Running single availability check")
        success = run_once(headless=headless)
        sys.exit(0 if success else 1)

    run_count = 0
    logger.info("Starting RentMasseur 24/7 availability keeper")
    logger.info("Check interval: %d minutes", args.interval)

    while True:
        run_count += 1
        logger.info("--- Run #%d at %s ---", run_count, datetime.now().isoformat())
        success = run_once(headless=headless)
        if success:
            logger.info("Run #%d completed successfully", run_count)
        else:
            logger.error("Run #%d failed", run_count)

        sleep_seconds = args.interval * 60
        logger.info("Sleeping for %d minutes...", args.interval)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
