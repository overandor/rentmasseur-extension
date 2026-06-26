#!/usr/bin/env python3
"""Login + dump profile edit page to find bio field."""
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
    
    print("\n[2] Profile edit page...")
    driver.get("https://rentmasseur.com/profile/edit")
    time.sleep(5)
    
    # Screenshot
    driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/profile_edit_page.png")
    print("  Screenshot saved")
    
    # Dump all editable elements
    info = driver.execute_script("""
        const result = {
            textareas: [],
            inputs: [],
            contenteditable: [],
            iframes: [],
            buttons: [],
            links: []
        };
        
        document.querySelectorAll('textarea').forEach(t => {
            result.textareas.push({id: t.id, name: t.name, value: (t.value||'').substring(0,100), visible: t.offsetParent !== null});
        });
        
        document.querySelectorAll('input').forEach(i => {
            result.inputs.push({type: i.type, id: i.id, name: i.name, value: (i.value||'').substring(0,50), placeholder: i.placeholder, visible: i.offsetParent !== null});
        });
        
        document.querySelectorAll('[contenteditable="true"], [contenteditable=""]').forEach(e => {
            result.contenteditable.push({tag: e.tagName, id: e.id, class: e.className, text: (e.innerText||'').substring(0,100)});
        });
        
        document.querySelectorAll('iframe').forEach(f => {
            result.iframes.push({src: (f.src||'').substring(0,80), id: f.id, name: f.name});
        });
        
        document.querySelectorAll('button').forEach(b => {
            result.buttons.push({text: (b.innerText||'').substring(0,30), type: b.type, id: b.id});
        });
        
        document.querySelectorAll('a').forEach(a => {
            if (a.innerText.trim()) result.links.push({text: a.innerText.trim().substring(0,30), href: a.href});
        });
        
        return result;
    """)
    
    print(f"\nTextareas: {len(info['textareas'])}")
    for t in info['textareas']:
        print(f"  id={t['id']} name={t['name']} visible={t['visible']} val={t['value'][:60]}")
    
    print(f"\nInputs: {len(info['inputs'])}")
    for i in info['inputs']:
        print(f"  type={i['type']} id={i['id']} name={i['name']} placeholder={i['placeholder']} visible={i['visible']}")
    
    print(f"\nContenteditable: {len(info['contenteditable'])}")
    for c in info['contenteditable']:
        print(f"  {c['tag']} id={c['id']} class={c['class']} text={c['text'][:60]}")
    
    print(f"\nIframes: {len(info['iframes'])}")
    for f in info['iframes']:
        print(f"  src={f['src']} id={f['id']}")
    
    print(f"\nButtons: {len(info['buttons'])}")
    for b in info['buttons']:
        print(f"  {b['text']} type={b['type']}")
    
    print(f"\nLinks: {len(info['links'])}")
    for l in info['links'][:20]:
        print(f"  {l['text']} -> {l['href']}")
    
    # Also dump page title and any SPA framework indicators
    print(f"\nTitle: {driver.title}")
    print(f"URL: {driver.current_url}")
    
    # Check for React/Vue/Angular
    frameworks = driver.execute_script("""
        return {
            react: !!document.querySelector('[data-reactroot]') || !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__,
            vue: !!window.__VUE__,
            angular: !!window.ng || !!document.querySelector('[ng-version]'),
            next: !!window.__NEXT_DATA__,
            nuxt: !!window.__NUXT__
        };
    """)
    print(f"Frameworks: {frameworks}")

finally:
    driver.quit()
    print("\nDone.")
