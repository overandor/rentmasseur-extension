#!/usr/bin/env python3
"""Login + find the actual profile edit page."""
import time, os
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")

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
    
    # Go to our own profile
    print("\n[2] Going to own profile...")
    driver.get(f"https://rentmasseur.com/{USERNAME}")
    time.sleep(5)
    print(f"  URL: {driver.current_url}")
    print(f"  Title: {driver.title}")
    
    # Get all links and buttons
    links = driver.execute_script("""
        return Array.from(document.querySelectorAll('a')).map(a => ({
            text: a.innerText.trim().substring(0,40), href: a.href, 
            onclick: a.getAttribute('onclick') || ''
        })).filter(a => a.text || a.onclick);
    """)
    print(f"\nLinks ({len(links)}):")
    for l in links[:40]:
        print(f"  {l['text'][:40]} -> {l['href']}")
    
    # Look for edit-related links
    edit_links = [l for l in links if any(w in (l['text'] + l['href']).lower() for w in ['edit', 'update', 'bio', 'about', 'profile', 'setting', 'account'])]
    print(f"\nEdit-related links ({len(edit_links)}):")
    for l in edit_links:
        print(f"  {l['text']} -> {l['href']}")
    
    # Check for buttons
    buttons = driver.execute_script("""
        return Array.from(document.querySelectorAll('button, [role="button"]')).map(b => ({
            text: (b.innerText||'').trim().substring(0,40), type: b.type, id: b.id,
            onclick: b.getAttribute('onclick') || ''
        })).filter(b => b.text);
    """)
    print(f"\nButtons ({len(buttons)}):")
    for b in buttons:
        print(f"  {b['text']} type={b['type']} onclick={b['onclick'][:40]}")
    
    # Check for textareas or contenteditable on profile page
    textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
    editables = driver.find_elements(By.CSS_SELECTOR, '[contenteditable]')
    print(f"\nTextareas: {len(textareas)}, Contenteditable: {len(editables)}")
    
    # Screenshot
    driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_page.png")
    print("Screenshot saved")
    
    # Try the Next.js __NEXT_DATA__ for clues
    next_data = driver.execute_script("""
        try {
            const el = document.getElementById('__NEXT_DATA__');
            if (el) return JSON.parse(el.textContent.substring(0, 2000));
        } catch(e) {}
        return null;
    """)
    if next_data:
        print(f"\nNext.js data keys: {list(next_data.keys())}")
        if 'props' in next_data:
            props = next_data['props']
            print(f"  props keys: {list(props.keys()) if isinstance(props, dict) else type(props)}")
        if 'page' in next_data:
            print(f"  page: {next_data['page']}")

finally:
    driver.quit()
    print("\nDone.")
