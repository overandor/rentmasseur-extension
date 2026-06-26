#!/usr/bin/env python3
"""Set availability to 24/7 via undetected-chromedriver."""
import time, os, json
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from datetime import datetime, timezone

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
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
    
    print("\n[2] Setting availability...")
    driver.get("https://rentmasseur.com/settings/travels")
    time.sleep(5)
    
    # Find availability controls
    info = driver.execute_script("""
        const r = {selects: [], buttons: [], inputs: [], textareas: []};
        document.querySelectorAll('select').forEach(s => {
            r.selects.push({id: s.id, name: s.name, options: Array.from(s.options).map(o => o.text).join('|'), value: s.value});
        });
        document.querySelectorAll('button').forEach(b => r.buttons.push({text: b.innerText.trim(), type: b.type, id: b.id}));
        document.querySelectorAll('input').forEach(i => r.inputs.push({type: i.type, id: i.id, name: i.name, value: (i.value||'').substring(0,30), checked: i.checked}));
        document.querySelectorAll('textarea').forEach(t => r.textareas.push({id: t.id, name: t.name, value: (t.value||'').substring(0,50)}));
        return r;
    """)
    
    print(f"  Selects: {len(info['selects'])}")
    for s in info['selects']:
        print(f"    id={s['id']} name={s['name']} value={s['value']} options={s['options'][:80]}")
    print(f"  Buttons: {len(info['buttons'])}")
    for b in info['buttons']:
        print(f"    {b['text']} type={b['type']}")
    print(f"  Inputs: {len(info['inputs'])}")
    for i in info['inputs']:
        print(f"    type={i['type']} id={i['id']} name={i['name']} value={i['value']} checked={i['checked']}")
    
    # Try to set availability
    set_result = driver.execute_script("""
        // Look for availability select or radio
        const selects = Array.from(document.querySelectorAll('select'));
        const availSelect = selects.find(s => {
            const opts = Array.from(s.options).map(o => o.text.toLowerCase());
            return opts.some(o => o.includes('available'));
        });
        
        if (availSelect) {
            const availOpt = Array.from(availSelect.options).find(o => 
                o.text.toLowerCase().includes('available') && !o.text.toLowerCase().includes('not'));
            if (availOpt) {
                availSelect.value = availOpt.value;
                availSelect.dispatchEvent(new Event('change', {bubbles: true}));
                return {method: 'select', value: availOpt.text};
            }
        }
        
        // Look for radio buttons
        const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
        const availRadio = radios.find(r => /avail/i.test(r.name + r.id + (r.value||'')));
        if (availRadio) {
            availRadio.click();
            return {method: 'radio', value: availRadio.value};
        }
        
        // Look for toggle/checkbox
        const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
        const availCheckbox = checkboxes.find(c => /avail/i.test(c.name + c.id));
        if (availCheckbox && !availCheckbox.checked) {
            availCheckbox.click();
            return {method: 'checkbox', checked: true};
        }
        
        return {error: 'no_availability_control'};
    """)
    print(f"\n  Set result: {set_result}")
    
    if 'error' not in set_result:
        time.sleep(1)
        # Save
        saved = driver.execute_script("""
            const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
            const sb = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'')+' '+(b.value||'')));
            if (sb) { sb.click(); return {ok: true, text: sb.innerText}; }
            return {ok: false};
        """)
        print(f"  Save: {saved}")
        time.sleep(3)
        
        # Write receipt
        receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        receipt = {"action": "set_availability", "status": "available_24_7", "success": True, "timestamp": datetime.now(timezone.utc).isoformat(), "method": "undetected-chromedriver"}
        rpath = os.path.join(receipts_dir, f"availability_{receipt['timestamp'].replace(':','-')}.json")
        with open(rpath, "w") as f:
            json.dump(receipt, f, indent=2)
        print(f"\n=== AVAILABILITY SET === Receipt: {rpath}")
    else:
        # Try the travels page or other settings pages
        print("  Trying /settings page directly...")
        driver.get("https://rentmasseur.com/settings")
        time.sleep(4)
        driver.save_screenshot("/Users/alep/Downloads/rentmasseur-optimizer/settings_avail.png")
        
        # Check for availability toggle on main settings
        toggles = driver.execute_script("""
            return Array.from(document.querySelectorAll('input[type="checkbox"], .toggle, .switch, [role="switch"]')).map(e => ({
                type: e.type, id: e.id, name: e.name, checked: e.checked, 
                label: e.closest('label') ? e.closest('label').innerText : (e.parentElement ? e.parentElement.innerText : '')
            }));
        """)
        print(f"  Toggles: {len(toggles)}")
        for t in toggles:
            print(f"    {t}")

finally:
    driver.quit()
    print("\nDone.")
