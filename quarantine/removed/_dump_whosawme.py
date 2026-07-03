#!/usr/bin/env python3
"""Quick dump of /settings/whosawme to find visitor structure."""
import time, os, json
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = uc.Chrome(options=options, version_main=149)

try:
    print("[1] Login...")
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
    print(f"  URL: {driver.current_url}")

    print("\n[2] /settings/whosawme...")
    driver.get("https://rentmasseur.com/settings/whosawme")
    time.sleep(5)
    print(f"  URL: {driver.current_url}")
    print(f"  Title: {driver.title}")

    # Dump all links
    links = driver.execute_script("""
        return Array.from(document.querySelectorAll('a')).map(a => ({
            href: a.href, text: a.innerText.trim().substring(0,60),
            cls: a.className, id: a.id
        })).filter(a => a.text || a.href);
    """)
    print(f"\nLinks: {len(links)}")
    for l in links[:40]:
        print(f"  {l['text'][:40]} -> {l['href'][:70]}")

    # Dump all images (visitor avatars)
    imgs = driver.execute_script("""
        return Array.from(document.querySelectorAll('img')).map(i => ({
            src: (i.src||'').substring(0,80), alt: i.alt, cls: i.className,
            parent_tag: i.parentElement ? i.parentElement.tagName : '',
            parent_href: i.parentElement && i.parentElement.tagName === 'A' ? i.parentElement.href : ''
        }));
    """)
    print(f"\nImages: {len(imgs)}")
    for i in imgs[:20]:
        print(f"  src={i['src'][:50]} alt={i['alt'][:20]} parent={i['parent_tag']} href={i['parent_href'][:60]}")

    # Dump page structure
    structure = driver.execute_script("""
        const body = document.body;
        const result = [];
        function walk(el, depth) {
            if (depth > 4) return;
            const tag = el.tagName.toLowerCase();
            const cls = el.className ? (typeof el.className === 'string' ? el.className.split(' ').slice(0,2).join('.') : '') : '';
            const id = el.id ? '#' + el.id : '';
            const text = (el.innerText || '').trim().substring(0, 30);
            if (text || cls || id) {
                result.push('  '.repeat(depth) + tag + id + (cls ? '.' + cls : '') + (text ? ' [' + text + ']' : ''));
            }
            Array.from(el.children).forEach(c => walk(c, depth + 1));
        }
        walk(body, 0);
        return result.slice(0, 80);
    """)
    print(f"\nPage structure:")
    for s in structure:
        print(s)

    driver.save_screenshot(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "rentmasseur-optimizer", "whosawme.png"))

finally:
    driver.quit()
    print("\nDone.")
