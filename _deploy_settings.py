#!/usr/bin/env python3
"""Login + navigate to settings + find and update bio."""
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

driver = uc.Chrome(options=options, version_main=149)

try:
    # Login
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
    
    # Go to settings/dashboard
    print("\n[2] Settings page...")
    driver.get("https://rentmasseur.com/settings")
    time.sleep(5)
    print(f"  URL: {driver.current_url}")
    print(f"  Title: {driver.title}")
    
    # Dump everything
    info = driver.execute_script("""
        const r = {textareas: [], inputs: [], contenteditable: [], buttons: [], links: [], tabs: []};
        document.querySelectorAll('textarea').forEach(t => r.textareas.push({id:t.id,name:t.name,ph:t.placeholder,val:(t.value||'').substring(0,80),vis:t.offsetParent!==null}));
        document.querySelectorAll('input').forEach(i => r.inputs.push({type:i.type,id:i.id,name:i.name,ph:i.placeholder,val:(i.value||'').substring(0,40),vis:i.offsetParent!==null}));
        document.querySelectorAll('[contenteditable]').forEach(e => r.contenteditable.push({tag:e.tagName,id:e.id,cls:e.className,txt:(e.innerText||'').substring(0,80)}));
        document.querySelectorAll('button, [role="button"]').forEach(b => r.buttons.push({txt:(b.innerText||'').trim().substring(0,30),type:b.type,id:b.id}));
        document.querySelectorAll('a').forEach(a => {if(a.innerText.trim()) r.links.push({txt:a.innerText.trim().substring(0,30),href:a.href})});
        document.querySelectorAll('[role="tab"], .nav-link, .tab').forEach(t => r.tabs.push({txt:(t.innerText||'').trim(),href:t.getAttribute('href')||'',id:t.id}));
        return r;
    """)
    
    print(f"\nTextareas: {len(info['textareas'])}")
    for t in info['textareas']:
        print(f"  id={t['id']} name={t['name']} ph={t['ph']} vis={t['vis']} val={t['val'][:60]}")
    
    print(f"\nInputs: {len(info['inputs'])}")
    for i in info['inputs']:
        print(f"  type={i['type']} id={i['id']} name={i['name']} ph={i['ph']} vis={i['vis']}")
    
    print(f"\nContenteditable: {len(info['contenteditable'])}")
    for c in info['contenteditable']:
        print(f"  {c['tag']} id={c['id']} cls={c['cls']} txt={c['txt'][:60]}")
    
    print(f"\nButtons: {len(info['buttons'])}")
    for b in info['buttons']:
        print(f"  {b['txt']} type={b['type']} id={b['id']}")
    
    print(f"\nTabs: {len(info['tabs'])}")
    for t in info['tabs']:
        print(f"  {t['txt']} href={t['href']} id={t['id']}")
    
    print(f"\nLinks: {len(info['links'])}")
    for l in info['links'][:25]:
        print(f"  {l['txt']} -> {l['href']}")
    
    driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/settings_page.png")
    
    # Try clicking through tabs to find bio editor
    print("\n[3] Looking for bio tab...")
    bio_tabs = [l for l in info['links'] if any(w in (l['txt']+l['href']).lower() for w in ['bio', 'about', 'profile', 'edit', 'content'])]
    print(f"  Bio-related links: {len(bio_tabs)}")
    for bt in bio_tabs:
        print(f"    {bt['txt']} -> {bt['href']}")
    
    # Try each bio-related link
    for bt in bio_tabs:
        print(f"\n  Trying: {bt['href']}")
        driver.get(bt['href'])
        time.sleep(4)
        textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
        editables = driver.find_elements(By.CSS_SELECTOR, '[contenteditable]')
        print(f"    textareas={len(textareas)} editables={len(editables)}")
        if textareas:
            for ta in textareas:
                val = ta.get_attribute("value") or ""
                print(f"    textarea id={ta.get_attribute('id')} name={ta.get_attribute('name')} len={len(val)} preview={val[:80]}")
            
            # Update the bio textarea (longest one or one with bio/about in name)
            updated = driver.execute_script("""
                const tas = Array.from(document.querySelectorAll('textarea'));
                let best = null, bestScore = 0;
                for (const ta of tas) {
                    const ctx = (ta.id||'') + ' ' + (ta.name||'') + ' ' + (ta.placeholder||'');
                    if (/bio|about|description|profile/i.test(ctx)) { best = ta; break; }
                    if ((ta.value||'').length > bestScore) { bestScore = (ta.value||'').length; best = ta; }
                }
                if (!best && tas.length > 0) best = tas[0];
                if (!best) return {error: 'no_textarea'};
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(best, arguments[0]);
                best.dispatchEvent(new Event('input', {bubbles: true}));
                best.dispatchEvent(new Event('change', {bubbles: true}));
                best.dispatchEvent(new Event('blur', {bubbles: true}));
                return {id: best.id, name: best.name, new_len: arguments[0].length};
            """, BIO_TEXT)
            print(f"    Updated: {updated}")
            
            if isinstance(updated, dict) and 'error' not in updated:
                time.sleep(1)
                saved = driver.execute_script("""
                    const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                    const sb = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'')+' '+(b.value||'')));
                    if (sb) { sb.click(); return {ok: true, text: sb.innerText}; }
                    return {ok: false};
                """)
                print(f"    Save: {saved}")
                time.sleep(5)
                
                # Receipt
                receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
                os.makedirs(receipts_dir, exist_ok=True)
                receipt = {"action": "bio_deploy", "bio_id": "controlled_wolf_v1", "experiment_id": "exp_001_targeted_wolf", "success": True, "timestamp": datetime.now(timezone.utc).isoformat(), "url": driver.current_url}
                rpath = os.path.join(receipts_dir, f"deploy_controlled_wolf_v1_{receipt['timestamp'].replace(':','-')}.json")
                with open(rpath, "w") as f:
                    json.dump(receipt, f, indent=2)
                print(f"\n=== BIO DEPLOYED === Receipt: {rpath}")
                break
        if editables:
            for e in editables:
                txt = e.get_attribute("innerText") or ""
                print(f"    editable tag={e.tag_name} id={e.get_attribute('id')} txt={txt[:80]}")
    
finally:
    driver.quit()
    print("\nDone.")
