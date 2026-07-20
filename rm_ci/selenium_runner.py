"""RM CI/CD Selenium Automator — proof, live-readonly, and approved-mutation modes.

Safety model:
  proof            → local control plane + extension + candidate tests only
  live_readonly    → can login to your own account, read pages, screenshot, no mutations
  approved_mutation → requires ADMIN_TOKEN + approved candidate, applies one change, verifies

Never: CAPTCHA bypass, anti-bot bypass, mass messaging, scraping, fake availability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from receipt_ledger import ReceiptLedger
from approval_gate import ApprovalGate
from report_builder import build_report


BASE_URL = "https://rentmasseur.com"
LOCAL_CP_URL = "http://localhost:7860"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


class RMSeleniumAutomator:
    def __init__(self, mode: str, artifacts: Path, registry_path: Path):
        self.mode = mode
        self.artifacts = artifacts
        self.screenshots = artifacts / "screenshots"
        self.receipts = ReceiptLedger(artifacts / "receipts")
        self.gate = ApprovalGate(mode)
        self.screenshots.mkdir(parents=True, exist_ok=True)
        self.registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        self.driver: Optional[webdriver.Chrome] = None
        self.functions_run: list[str] = []

    def _make_driver(self):
        options = Options()
        if self.mode != "live_readonly":
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1200")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if os.getenv("RM_CHROME_BINARY"):
            options.binary_location = os.getenv("RM_CHROME_BINARY")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        return driver

    def _ensure_driver(self):
        if not self.driver:
            self.driver = self._make_driver()

    def screenshot(self, name: str) -> str:
        self._ensure_driver()
        path = self.screenshots / f"{int(time.time())}_{name}.png"
        try:
            self.driver.save_screenshot(str(path))
        except Exception:
            return ""
        return str(path)

    def page_text(self) -> str:
        try:
            return self.driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        except Exception:
            return ""

    def detect_block(self) -> Optional[str]:
        txt = self.page_text().lower()
        url = (self.driver.current_url or "").lower()
        needles = [
            ("captcha", "captcha_detected"),
            ("crowdsec", "crowdsec_detected"),
            ("access forbidden", "access_forbidden"),
            ("verify you are human", "human_verification"),
            ("unusual traffic", "traffic_challenge"),
            ("too many requests", "rate_limited"),
        ]
        for needle, reason in needles:
            if needle in txt or needle in url:
                return reason
        return None

    # ── Handlers ──────────────────────────────────────────────────────

    def run_health_check(self):
        try:
            r = requests.get(f"{LOCAL_CP_URL}/api/health", timeout=10)
            self.receipts.write("health_check", "pass", {
                "status_code": r.status_code,
                "body_hash": sha256_text(r.text),
                "body_preview": r.text[:500],
            })
        except Exception as e:
            self.receipts.write("health_check", "fail", {"error": str(e)})

    def run_metrics_ingest(self):
        payload = {
            "source": "ci_selenium",
            "event": "proof_metric",
            "ts": int(time.time()),
            "value": 1,
        }
        try:
            r = requests.post(f"{LOCAL_CP_URL}/api/metrics/ingest", json=payload, timeout=10)
            self.receipts.write("metrics_ingest", "pass", {
                "status_code": r.status_code,
                "response_hash": sha256_text(r.text),
            })
        except Exception as e:
            self.receipts.write("metrics_ingest", "fail", {"error": str(e)})

    def run_local_dashboard_snapshot(self):
        self._ensure_driver()
        try:
            self.driver.get(LOCAL_CP_URL)
            time.sleep(2)
            shot = self.screenshot("local_dashboard")
            title = self.driver.title
            body = self.page_text()[:2000]
            self.receipts.write("local_dashboard_snapshot", "pass", {
                "title": title,
                "body_hash": sha256_text(body),
                "screenshot": shot,
            })
        except Exception as e:
            self.receipts.write("local_dashboard_snapshot", "fail", {"error": str(e)})

    def run_bio_candidate_generate(self):
        try:
            r = requests.post(
                f"{LOCAL_CP_URL}/api/run/ga-rl",
                headers={"Authorization": f"Bearer {os.getenv('ADMIN_TOKEN', '')}"},
                timeout=120,
            )
            self.receipts.write("bio_candidate_generate", "pass", {
                "status_code": r.status_code,
                "response_hash": sha256_text(r.text),
                "response_preview": r.text[:1000],
            })
        except Exception as e:
            self.receipts.write("bio_candidate_generate", "fail", {"error": str(e)})

    def run_bio_candidate_preview(self):
        try:
            r = requests.get(f"{LOCAL_CP_URL}/api/candidates", timeout=10)
            self.receipts.write("bio_candidate_preview", "pass", {
                "status_code": r.status_code,
                "candidate_count": len(r.json()) if r.headers.get("content-type", "").startswith("application/json") else 0,
                "response_hash": sha256_text(r.text),
            })
        except Exception as e:
            self.receipts.write("bio_candidate_preview", "fail", {"error": str(e)})

    def run_live_login_readonly(self):
        self._ensure_driver()
        username = os.getenv("RM_USERNAME") or os.getenv("RM_USER")
        password = os.getenv("RM_PASSWORD") or os.getenv("RM_PASS")

        if not username or not password:
            self.receipts.write("live_login_readonly", "skipped", {
                "reason": "missing_credentials"
            })
            return

        try:
            self.driver.get(f"{BASE_URL}/login")
            time.sleep(3)
            shot = self.screenshot("login_page")

            block = self.detect_block()
            if block:
                self.receipts.write("live_login_readonly", "blocked", {
                    "reason": block,
                    "screenshot": shot,
                })
                return

            self.receipts.write("live_login_readonly", "manual_required", {
                "reason": "login selectors must be confirmed manually before CI login is enabled",
                "screenshot": shot,
            })
        except Exception as e:
            self.receipts.write("live_login_readonly", "fail", {"error": str(e)})

    def run_dashboard_snapshot(self):
        self._ensure_driver()
        try:
            self.driver.get(f"{BASE_URL}/settings")
            time.sleep(4)
            shot = self.screenshot("dashboard")
            block = self.detect_block()
            if block:
                self.receipts.write("dashboard_snapshot", "blocked", {
                    "reason": block, "screenshot": shot,
                })
                return
            txt = self.page_text()
            self.receipts.write("dashboard_snapshot", "pass", {
                "title": self.driver.title,
                "text_len": len(txt),
                "body_hash": sha256_text(txt[:2000]),
                "screenshot": shot,
                "signals": {
                    "availability": "availability" in txt.lower(),
                    "profile": "profile" in txt.lower(),
                    "statistics": "statistics" in txt.lower() or "views" in txt.lower(),
                    "messages": "messages" in txt.lower() or "mailbox" in txt.lower(),
                },
            })
        except Exception as e:
            self.receipts.write("dashboard_snapshot", "fail", {"error": str(e)})

    def run_availability_read(self):
        self._ensure_driver()
        try:
            self.driver.get(f"{BASE_URL}/settings?availability=1")
            time.sleep(4)
            shot = self.screenshot("availability")
            block = self.detect_block()
            if block:
                self.receipts.write("availability_read", "blocked", {
                    "reason": block, "screenshot": shot,
                })
                return
            txt = self.page_text()
            self.receipts.write("availability_read", "pass", {
                "text_len": len(txt),
                "available_present": "available" in txt.lower(),
                "screenshot": shot,
            })
        except Exception as e:
            self.receipts.write("availability_read", "fail", {"error": str(e)})

    def run_bio_field_detect(self):
        self._ensure_driver()
        try:
            self.driver.get(f"{BASE_URL}/settings/about")
            time.sleep(4)
            shot = self.screenshot("bio_field_detect")
            block = self.detect_block()
            if block:
                self.receipts.write("bio_field_detect", "blocked", {
                    "reason": block, "screenshot": shot,
                })
                return

            selectors_found = {}
            for label, sels in {
                "textarea": ["textarea[name*='description' i]", "textarea[name*='bio' i]", "textarea"],
                "contenteditable": ["[contenteditable='true']"],
                "save_button": ["button[type='submit']"],
            }.items():
                for sel in sels:
                    try:
                        els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        if els and any(e.is_displayed() for e in els):
                            selectors_found[label] = sel
                            break
                    except Exception:
                        continue

            # Save selector proof for approved_mutation mode
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            proof_path = debug_dir / "bio_apply_live_selectors.json"
            proof_path.write_text(json.dumps(selectors_found, indent=2), encoding="utf-8")

            self.receipts.write("bio_field_detect", "pass", {
                "screenshot": shot,
                "selectors_found": selectors_found,
                "selector_proof": str(proof_path),
            })
        except Exception as e:
            self.receipts.write("bio_field_detect", "fail", {"error": str(e)})

    def run_extension_popup_smoke(self):
        self._ensure_driver()
        try:
            popup_path = Path("popup.html").resolve()
            self.driver.get(f"file://{popup_path}")
            time.sleep(2)
            shot = self.screenshot("extension_popup")
            title = self.driver.title
            self.receipts.write("extension_popup_smoke", "pass", {
                "title": title,
                "screenshot": shot,
            })
        except Exception as e:
            self.receipts.write("extension_popup_smoke", "fail", {"error": str(e)})

    def run_extension_content_script_smoke(self):
        self._ensure_driver()
        try:
            self.driver.get(BASE_URL)
            time.sleep(3)
            shot = self.screenshot("extension_content_script")
            self.receipts.write("extension_content_script_smoke", "pass", {
                "url": self.driver.current_url,
                "screenshot": shot,
            })
        except Exception as e:
            self.receipts.write("extension_content_script_smoke", "fail", {"error": str(e)})

    # ── Approved mutation handlers ────────────────────────────────────

    def run_bio_apply_live(self, candidate_file: str = "", approval_token: str = ""):
        if not self.gate.verify_approval_token(approval_token):
            self.receipts.write("bio_apply_live", "blocked", {
                "reason": "approval_token_mismatch_or_missing"
            })
            return
        if not self.gate.check_selector_proof("bio_apply_live"):
            self.receipts.write("bio_apply_live", "blocked", {
                "reason": "no_selector_proof_run_bio_field_detect_first"
            })
            return
        candidate = self.gate.load_candidate(candidate_file)
        if not candidate:
            self.receipts.write("bio_apply_live", "blocked", {
                "reason": "no_candidate_file"
            })
            return

        bio_text = candidate.get("bio", "")
        if len(bio_text) < 40 or len(bio_text) > 3000:
            self.receipts.write("bio_apply_live", "blocked", {
                "reason": "bio_length_out_of_bounds",
                "length": len(bio_text),
            })
            return

        risky = ["escort", "happy ending", "nude", "naked", "sex", "guaranteed cure"]
        if any(x in bio_text.lower() for x in risky):
            self.receipts.write("bio_apply_live", "blocked", {
                "reason": "bio_failed_local_policy_filter"
            })
            return

        self._ensure_driver()
        try:
            self.driver.get(f"{BASE_URL}/settings/about")
            time.sleep(4)
            before_shot = self.screenshot("bio_before")

            block = self.detect_block()
            if block:
                self.receipts.write("bio_apply_live", "blocked", {
                    "reason": block, "screenshot": before_shot,
                })
                return

            field = None
            for sel in ["textarea[name*='description' i]", "textarea[name*='bio' i]", "textarea", "[contenteditable='true']"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed():
                            field = el
                            break
                except Exception:
                    continue
                if field:
                    break

            if not field:
                self.receipts.write("bio_apply_live", "fail", {
                    "reason": "bio_field_not_found",
                    "screenshot": before_shot,
                })
                return

            tag = field.tag_name.lower()
            if tag == "textarea":
                field.clear()
                field.send_keys(bio_text)
            else:
                self.driver.execute_script(
                    "arguments[0].innerText = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
                    field, bio_text,
                )

            time.sleep(1)
            after_fill_shot = self.screenshot("bio_after_fill")

            saved = False
            for sel in ["button[type='submit']"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            self.driver.execute_script("arguments[0].click();", el)
                            saved = True
                            break
                except Exception:
                    continue
                if saved:
                    break

            time.sleep(4)
            after_shot = self.screenshot("bio_after_save")
            block = self.detect_block()

            self.receipts.write("bio_apply_live", "pass" if saved and not block else "fail", {
                "clicked_save": saved,
                "bio_chars": len(bio_text),
                "before_screenshot": before_shot,
                "after_fill_screenshot": after_fill_shot,
                "after_screenshot": after_shot,
                "block_detected": block,
            })
        except Exception as e:
            self.receipts.write("bio_apply_live", "fail", {"error": str(e)})

    def run_availability_set_live(self, candidate_file: str = "", approval_token: str = ""):
        if not self.gate.verify_approval_token(approval_token):
            self.receipts.write("availability_set_live", "blocked", {
                "reason": "approval_token_mismatch_or_missing"
            })
            return

        self._ensure_driver()
        try:
            self.driver.get(f"{BASE_URL}/settings?availability=1")
            time.sleep(4)
            before_shot = self.screenshot("availability_before")

            block = self.detect_block()
            if block:
                self.receipts.write("availability_set_live", "blocked", {
                    "reason": block, "screenshot": before_shot,
                })
                return

            clicked = False
            for sel in ["label", "button"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        txt = (el.text or "").lower()
                        if "available" in txt and el.is_displayed():
                            self.driver.execute_script("arguments[0].click();", el)
                            clicked = True
                            break
                except Exception:
                    continue
                if clicked:
                    break

            time.sleep(1)
            saved = False
            for sel in ["button[type='submit']"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed() and el.is_enabled():
                            self.driver.execute_script("arguments[0].click();", el)
                            saved = True
                            break
                except Exception:
                    continue
                if saved:
                    break

            time.sleep(3)
            after_shot = self.screenshot("availability_after")
            block = self.detect_block()

            self.receipts.write("availability_set_live", "pass" if clicked and saved and not block else "fail", {
                "clicked_available": clicked,
                "clicked_save": saved,
                "before_screenshot": before_shot,
                "after_screenshot": after_shot,
                "block_detected": block,
            })
        except Exception as e:
            self.receipts.write("availability_set_live", "fail", {"error": str(e)})

    # ── Dispatcher ────────────────────────────────────────────────────

    HANDLERS = {
        "health_check": "run_health_check",
        "metrics_ingest": "run_metrics_ingest",
        "local_dashboard_snapshot": "run_local_dashboard_snapshot",
        "bio_candidate_generate": "run_bio_candidate_generate",
        "bio_candidate_preview": "run_bio_candidate_preview",
        "live_login_readonly": "run_live_login_readonly",
        "dashboard_snapshot": "run_dashboard_snapshot",
        "availability_read": "run_availability_read",
        "bio_field_detect": "run_bio_field_detect",
        "extension_popup_smoke": "run_extension_popup_smoke",
        "extension_content_script_smoke": "run_extension_content_script_smoke",
        "bio_apply_live": "run_bio_apply_live",
        "availability_set_live": "run_availability_set_live",
    }

    def run_function(self, name: str, cfg: dict, candidate_file: str = "", approval_token: str = ""):
        self.functions_run.append(name)

        block_reason = self.gate.is_blocked(name, cfg)
        if block_reason:
            self.receipts.write(name, "blocked", {"reason": block_reason})
            return

        handler_name = self.HANDLERS.get(name)
        if not handler_name:
            self.receipts.write(name, "skipped", {"reason": "no_handler_implemented"})
            return

        handler = getattr(self, handler_name)
        try:
            if name in ("bio_apply_live", "availability_set_live"):
                handler(candidate_file=candidate_file, approval_token=approval_token)
            else:
                handler()
        except Exception as e:
            self.receipts.write(name, "fail", {"error": str(e)})

        time.sleep(float(os.getenv("RM_ACTION_PAUSE_SECONDS", "2.0")))

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


def main():
    parser = argparse.ArgumentParser(description="RM CI/CD Selenium Automator")
    parser.add_argument("--registry", required=True, help="Path to function_registry.yml")
    parser.add_argument("--mode", default="proof", choices=["proof", "live_readonly", "approved_mutation"])
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--function", default="all_safe", help="Function name or 'all_safe'")
    parser.add_argument("--candidate-file", default="", help="Approved candidate JSON for mutations")
    parser.add_argument("--approval-token", default="", help="ADMIN_TOKEN for approved_mutation mode")
    args = parser.parse_args()

    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    registry_path = Path(args.registry)

    automator = RMSeleniumAutomator(args.mode, artifacts, registry_path)

    try:
        functions = automator.registry.get("functions", {})

        if args.function == "all_safe":
            run_list = [(name, cfg) for name, cfg in functions.items() if cfg.get("allowed_in_ci", False)]
        else:
            cfg = functions.get(args.function)
            if not cfg:
                print(json.dumps({"error": f"unknown_function: {args.function}"}), file=sys.stderr)
                sys.exit(2)
            run_list = [(args.function, cfg)]

        for name, cfg in run_list:
            automator.run_function(
                name, cfg,
                candidate_file=args.candidate_file,
                approval_token=args.approval_token,
            )

    finally:
        automator.close()

    # Build report
    report_path = build_report(
        artifacts / "receipts", artifacts, args.mode, automator.functions_run
    )

    # Print summary
    ledger_valid = automator.receipts.verify()
    print(json.dumps({
        "mode": args.mode,
        "functions_run": automator.functions_run,
        "ledger_valid": ledger_valid,
        "report": str(report_path),
        "artifacts": str(artifacts),
    }, indent=2))

    sys.exit(0 if ledger_valid else 1)


if __name__ == "__main__":
    main()
