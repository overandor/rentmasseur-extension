"""Chrome driver setup, explicit waits, screenshots, HTML capture."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = os.getenv("RM_BASE_URL", "https://rentmasseur.com").rstrip("/")
SCREENSHOT_DIR = Path("screenshots")
DEBUG_DIR = Path("debug")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def build_driver(headless: bool = True) -> WebDriver:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,1200")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if os.getenv("RM_CHROME_BINARY"):
        opts.binary_location = os.getenv("RM_CHROME_BINARY")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(int(os.getenv("RM_PAGE_TIMEOUT", "45")))
    # Use explicit waits only — do NOT set implicit_wait to avoid unpredictable behavior.
    return driver


def safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)[:80]


def capture(driver: WebDriver, action: str) -> Tuple[Optional[str], Optional[str]]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"{ts}_{safe_name(action)}"
    screenshot_path = SCREENSHOT_DIR / f"{base}.png"
    html_path = DEBUG_DIR / f"{base}.html"
    try:
        driver.save_screenshot(str(screenshot_path))
    except Exception:
        screenshot_path = None
    try:
        html_path.write_text(driver.page_source or "", encoding="utf-8", errors="ignore")
    except Exception:
        html_path = None
    return (str(screenshot_path) if screenshot_path else None,
            str(html_path) if html_path else None)


def page_text(driver: WebDriver) -> str:
    try:
        return driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        return ""


def wait_for(driver: WebDriver, by: str, selector: str, timeout: int = 10):
    """Explicit wait for element visibility."""
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, selector))
    )


def wait_for_clickable(driver: WebDriver, by: str, selector: str, timeout: int = 10):
    """Explicit wait for element clickability."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )


def wait_for_url_contains(driver: WebDriver, fragment: str, timeout: int = 10) -> bool:
    """Explicit wait for URL to contain a fragment."""
    try:
        WebDriverWait(driver, timeout).until(EC.url_contains(fragment))
        return True
    except Exception:
        return False


def find_visible(driver: WebDriver, by: str, selector: str):
    """Find first visible element matching selector."""
    try:
        els = driver.find_elements(by, selector)
        for el in els:
            if el.is_displayed() and el.is_enabled():
                return el
    except Exception:
        pass
    return None


def click_first(driver: WebDriver, candidates: list[tuple[str, str]]) -> bool:
    for by, sel in candidates:
        el = find_visible(driver, by, sel)
        if el:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", el)
            return True
    return False


def get_credentials() -> tuple[str, str]:
    user = os.getenv("RM_USER") or os.getenv("RENTMASSEUR_USERNAME") or ""
    pwd = os.getenv("RM_PASS") or os.getenv("RENTMASSEUR_PASSWORD") or ""
    return user, pwd
