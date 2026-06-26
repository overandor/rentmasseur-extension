#!/usr/bin/env python3
"""
Post interview answers to RentMasseur profile.

Usage:
    python3 post_interview.py --answers '{"question":"What is your style?","answer":"Deep tissue focused..."}'
    python3 post_interview.py --file content/interview/answers.json
"""
import time, os, sys, json, argparse
import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from datetime import datetime, timezone

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

USERNAME = os.getenv("RENTMASSEUR_USERNAME", "")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "")
INTERVIEW_URL = "https://rentmasseur.com/settings/interview"


def login(driver):
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
    return "login" not in driver.current_url.lower()


def post_interview(driver, answers):
    """Post interview answers. answers = list of {question, answer} or {question_id, answer}."""
    driver.get(INTERVIEW_URL)
    time.sleep(5)

    # Scrape available questions
    print("  Scraping interview questions...")
    questions = driver.execute_script("""
        const result = [];
        // Look for question elements
        const qEls = document.querySelectorAll('.interview-question, .question, [data-question], .card-title, h3, h4, label, .form-label');
        qEls.forEach((el, i) => {
            const text = el.innerText.trim();
            if (text && text.endsWith('?') && text.length > 10) {
                // Find associated textarea
                let textarea = null;
                let parent = el.closest('.form-group, .card, .mb-3, .field, .interview-item, .form-row') || el.parentElement;
                if (parent) {
                    textarea = parent.querySelector('textarea');
                }
                if (!textarea) {
                    textarea = document.querySelectorAll('textarea')[i];
                }
                result.push({
                    question: text,
                    textarea_id: textarea ? textarea.id : null,
                    textarea_name: textarea ? textarea.name : null,
                    index: i
                });
            }
        });
        return result;
    """)
    print(f"  Found {len(questions)} questions")
    for q in questions[:5]:
        print(f"    [{q['index']}] {q['question'][:60]}... (textarea: {q['textarea_id']})")

    # Fill answers
    filled = 0
    for ans in answers:
        question_text = ans.get('question', '').lower()
        answer_text = ans.get('answer', '')
        question_id = ans.get('question_id')

        # Match question
        matched = None
        if question_id is not None and question_id < len(questions):
            matched = questions[question_id]
        else:
            matched = questions.find(lambda q: question_text in q['question'].lower()) if hasattr(questions, 'find') else None
            if not matched:
                for q in questions:
                    if question_text and question_text in q['question'].lower():
                        matched = q
                        break

        if not matched:
            print(f"  No match for: {question_text[:40]}")
            continue

        # Fill textarea
        result = driver.execute_script("""
            const textareas = document.querySelectorAll('textarea');
            const ta = textareas[arguments[0]] || document.getElementById(arguments[1]) || document.querySelector(`textarea[name="${arguments[1]}"]`);
            if (!ta) return {error: 'no_textarea'};
            const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            ns.call(ta, arguments[2]);
            ta.dispatchEvent(new Event('input', {bubbles: true}));
            ta.dispatchEvent(new Event('change', {bubbles: true}));
            return {id: ta.id, name: ta.name, len: arguments[2].length};
        """, matched['index'], matched.get('textarea_id') or matched.get('textarea_name'), answer_text)
        print(f"  Filled: {matched['question'][:40]}... -> {result}")
        if isinstance(result, dict) and 'error' not in result:
            filled += 1
        time.sleep(0.5)

    if filled == 0:
        return False, {"error": "no_questions_matched", "questions_found": len(questions)}

    time.sleep(1)

    # Save
    saved = driver.execute_script("""
        const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
        const sb = btns.find(b => /save|update|submit|apply|confirm/i.test((b.innerText||'') + ' ' + (b.value||'')));
        if (sb) { sb.click(); return {ok: true, text: sb.innerText || sb.value}; }
        return {ok: false};
    """)
    print(f"  Save: {saved}")
    time.sleep(5)

    return saved.get('ok', False), {"filled": filled, "save": saved}


def write_receipt(action, data, success=True):
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt = {"action": action, "success": success, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    rpath = os.path.join(receipts_dir, f"{action}_{receipt['timestamp'].replace(':','-')}.json")
    with open(rpath, "w") as f:
        json.dump(receipt, f, indent=2)
    return rpath


def main():
    parser = argparse.ArgumentParser(description="Post interview answers to RentMasseur")
    parser.add_argument("--answers", required=False, help="JSON array of {question, answer}")
    parser.add_argument("--file", required=False, help="JSON file with answers array")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r") as f:
            answers = json.load(f)
    elif args.answers:
        answers = json.loads(args.answers)
    else:
        print("Error: --answers or --file required")
        sys.exit(1)

    if isinstance(answers, dict):
        answers = [answers]

    print(f"Answers to post: {len(answers)}")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=149)

    try:
        print("\n[1] Login...")
        if not login(driver):
            print("  Login failed!")
            sys.exit(1)

        print("\n[2] Posting interview answers...")
        success, details = post_interview(driver, answers)

        rpath = write_receipt("post_interview", {"answers_count": len(answers), "details": details}, success)
        if success:
            print(f"\n=== INTERVIEW POSTED === Receipt: {rpath}")
        else:
            print(f"\n=== INTERVIEW POST FAILED === Receipt: {rpath}")
            sys.exit(1)

    finally:
        driver.quit()
        print("\nDone.")


if __name__ == "__main__":
    main()
