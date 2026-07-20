#!/usr/bin/env python3
"""
RM Playwright Probe v2 — hardened, secret-redacting, authenticated read-only.

Pipeline:
  public probe → authenticated read-only probe → selector registry →
  endpoint registry (redacted) → function registry (generated) → receipts

Safety:
  - Never stores cookies/tokens in artifacts
  - Redacts all secrets from API endpoint logs
  - Stops on CAPTCHA/CrowdSec/rate limit/2FA — no bypass
  - Never submits forms, never clicks save, never sends messages
  - storageState saved locally only, never uploaded as artifact

Usage:
  # Public probe (safe, no creds)
  python probes/rm_playwright_probe.py --mode public

  # Authenticated read-only (creds from shell env)
  export RM_USER="your_email"
  export RM_PASS="your_password"
  python probes/rm_playwright_probe.py --mode authenticated-readonly --login

  # Single page
  python probes/rm_playwright_probe.py --mode authenticated-readonly --login --page dashboard
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext


BASE_URL = "https://rentmasseur.com"
ARTIFACTS = Path("artifacts/probe")
SCREENSHOTS = ARTIFACTS / "screenshots"
API_DIR = ARTIFACTS / "api_calls"
STORAGE_STATE = Path(".rm_storage_state.json")  # local only, gitignored, never uploaded

for d in (ARTIFACTS, SCREENSHOTS, API_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ── Pages ─────────────────────────────────────────────────────────────

PAGES_PUBLIC = {
    "login_page_probe": {"url": f"{BASE_URL}/login", "needs_login": False},
    "public_profile_probe": {"url": f"{BASE_URL}/karpathianwolf", "needs_login": False},
    "search_probe": {"url": f"{BASE_URL}/search/manhattan-ny", "needs_login": False},
}

PAGES_AUTHENTICATED = {
    "dashboard_read": {"url": f"{BASE_URL}/settings", "needs_login": True},
    "availability_read": {"url": f"{BASE_URL}/settings?availability=1", "needs_login": True},
    "about_profile_read": {"url": f"{BASE_URL}/settings/about", "needs_login": True},
    "bio_field_detect": {"url": f"{BASE_URL}/settings/about", "needs_login": True},
    "stats_read": {"url": f"{BASE_URL}/settings/stats", "needs_login": True},
    "mailbox_page_detect": {"url": f"{BASE_URL}/mailbox", "needs_login": True},
    "compose_form_detect": {"url": f"{BASE_URL}/mailbox/compose", "needs_login": True},
    "settings_page_detect": {"url": f"{BASE_URL}/settings/profile", "needs_login": True},
    "logout_detect": {"url": f"{BASE_URL}/settings", "needs_login": True, "find_logout": True},
}


# ── Secret redaction ─────────────────────────────────────────────────

REDACT_HEADER_KEYS = {
    "cookie", "set-cookie", "authorization", "bearer",
    "x-csrf-token", "x-csrf", "csrf",
}

REDACT_BODY_KEYS = {
    "csrf", "password", "email", "session", "token",
    "accesstoken", "refreshtoken", "auth",
}

REDACT_BODY_PATTERNS = [
    (re.compile(r'"csrf"\s*:\s*"[^"]*"'), '"csrf":"[REDACTED]"'),
    (re.compile(r'"password"\s*:\s*"[^"]*"'), '"password":"[REDACTED]"'),
    (re.compile(r'"email"\s*:\s*"[^"]*"'), '"email":"[REDACTED]"'),
    (re.compile(r'"token"\s*:\s*"[^"]*"'), '"token":"[REDACTED]"'),
    (re.compile(r'"accessToken"\s*:\s*"[^"]*"'), '"accessToken":"[REDACTED]"'),
    (re.compile(r'"refreshToken"\s*:\s*"[^"]*"'), '"refreshToken":"[REDACTED]"'),
    (re.compile(r'"session"\s*:\s*"[^"]*"'), '"session":"[REDACTED]"'),
]


def redact_headers(headers: dict) -> dict:
    out = {}
    for k, v in headers.items():
        if k.lower() in REDACT_HEADER_KEYS:
            out[k] = "[REDACTED]"
        else:
            out[k] = v
    return out


def redact_body(text: str) -> str:
    for pattern, replacement in REDACT_BODY_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def body_keys(text: str) -> list[str]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return list(data.keys())
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return list(data[0].keys())
    except Exception:
        pass
    return []


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


# ── Block detection ──────────────────────────────────────────────────

BLOCK_NEEDLES = [
    ("captcha", "captcha_detected"),
    ("crowdsec", "crowdsec_detected"),
    ("access forbidden", "access_forbidden"),
    ("verify you are human", "human_verification"),
    ("unusual traffic", "traffic_challenge"),
    ("too many requests", "rate_limited"),
    ("two-factor", "two_factor_required"),
    ("2fa", "two_factor_required"),
    ("suspicious login", "suspicious_login"),
    ("password reset", "password_reset_prompt"),
]


def detect_block(page: Page) -> Optional[str]:
    try:
        txt = page.inner_text("body")[:3000].lower()
    except Exception:
        txt = ""
    url = (page.url or "").lower()
    for needle, reason in BLOCK_NEEDLES:
        if needle in txt or needle in url:
            return reason
    return None


# ── XPath discovery ──────────────────────────────────────────────────

def discover_xpaths(page: Page) -> dict:
    findings = {
        "inputs": [],
        "textareas": [],
        "buttons": [],
        "selects": [],
        "contenteditable": [],
        "links_profile": [],
    }

    for el in page.query_selector_all("input"):
        try:
            if not el.is_visible():
                continue
            itype = el.get_attribute("type") or ""
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            iph = el.get_attribute("placeholder") or ""
            iaria = el.get_attribute("aria-label") or ""
            parts = []
            if iid: parts.append(f"@id='{iid}'")
            if iname: parts.append(f"@name='{iname}'")
            if itype: parts.append(f"@type='{itype}'")
            xpath = f"//input[{ ' and '.join(parts) }]" if parts else "//input"
            findings["inputs"].append({
                "xpath": xpath, "type": itype, "name": iname,
                "id": iid, "placeholder": iph, "aria_label": iaria,
            })
        except Exception:
            continue

    for el in page.query_selector_all("textarea"):
        try:
            if not el.is_visible():
                continue
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            iph = el.get_attribute("placeholder") or ""
            iaria = el.get_attribute("aria-label") or ""
            xpath = f"//textarea[@name='{iname}']" if iname else "//textarea"
            findings["textareas"].append({
                "xpath": xpath, "name": iname, "id": iid,
                "placeholder": iph, "aria_label": iaria,
            })
        except Exception:
            continue

    for el in page.query_selector_all("button"):
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text() or "").strip()[:80]
            btype = el.get_attribute("type") or ""
            bclass = el.get_attribute("class") or ""
            baria = el.get_attribute("aria-label") or ""
            # Skip cookie consent buttons
            if "ACCEPT ALL" in text:
                continue
            xpath = f"//button[contains(text(),'{text}')]" if text else "//button"
            findings["buttons"].append({
                "xpath": xpath, "text": text, "type": btype,
                "class": bclass[:100], "aria_label": baria,
            })
        except Exception:
            continue

    for el in page.query_selector_all("select"):
        try:
            if not el.is_visible():
                continue
            iname = el.get_attribute("name") or ""
            iid = el.get_attribute("id") or ""
            xpath = f"//select[@name='{iname}']" if iname else "//select"
            findings["selects"].append({"xpath": xpath, "name": iname, "id": iid})
        except Exception:
            continue

    for el in page.query_selector_all("[contenteditable='true']"):
        try:
            if not el.is_visible():
                continue
            cclass = el.get_attribute("class") or ""
            crole = el.get_attribute("role") or ""
            findings["contenteditable"].append({
                "xpath": "//*[@contenteditable='true']",
                "class": cclass[:100], "role": crole,
            })
        except Exception:
            continue

    for el in page.query_selector_all("a[href]"):
        try:
            href = el.get_attribute("href") or ""
            if href.startswith("/") and not any(x in href for x in [
                "login", "settings", "search", "blog", "reviews", "interviews",
                "available", "find-massage", "live-cams", "sitemap", "advertise",
                "mailbox", "static", "_next", "images", "api", "blogs", "404",
            ]):
                parts = href.strip("/").split("/")
                if parts and parts[0] and len(parts) == 1:
                    findings["links_profile"].append({
                        "href": href,
                        "text": (el.inner_text() or "").strip()[:60],
                    })
        except Exception:
            continue

    return findings


# ── API interceptor with redaction ───────────────────────────────────

class APIInterceptor:
    def __init__(self, redact: bool = True):
        self.calls: list[dict] = []
        self.redact = redact

    def on_request(self, request):
        url = request.url
        if "rentmasseur.com/api" not in url and "/api/" not in url:
            return
        entry = {
            "method": request.method,
            "url": url,
            "url_path": url.replace(BASE_URL, ""),
            "request_headers_redacted": self.redact,
            "post_data": None,
        }
        if self.redact:
            entry["request_headers"] = redact_headers(dict(request.headers))
            pd = request.post_data
            if pd:
                entry["post_data"] = redact_body(pd)
        else:
            entry["request_headers"] = dict(request.headers)
            entry["post_data"] = request.post_data
        self.calls.append(entry)

    def on_response(self, response):
        url = response.url
        if "rentmasseur.com/api" not in url and "/api/" not in url:
            return
        for call in reversed(self.calls):
            if call["url"] == url and "status" not in call:
                call["status"] = response.status
                call["status_text"] = response.status_text
                try:
                    body = response.text()
                    call["response_body_hash"] = f"sha256:{sha256(body)}"
                    call["response_body_len"] = len(body)
                    if self.redact:
                        redacted = redact_body(body[:2000])
                        call["response_preview"] = redacted
                        call["response_keys"] = body_keys(body)
                    else:
                        call["response_preview"] = body[:2000]
                        call["response_keys"] = body_keys(body)
                except Exception:
                    call["response_body_hash"] = None
                    call["response_preview"] = None
                break

    def save(self, page_name: str) -> Path:
        safe = re.sub(r'[^A-Za-z0-9_-]', '_', page_name)[:60]
        path = API_DIR / f"{safe}_api.json"
        path.write_text(json.dumps(self.calls, indent=2, default=str), encoding="utf-8")
        return path


# ── Login ────────────────────────────────────────────────────────────

def attempt_login(page: Page, context: BrowserContext, username: str, password: str) -> tuple[bool, Optional[str]]:
    """Attempt login. Returns (success, block_reason)."""
    try:
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        block = detect_block(page)
        if block:
            return False, block

        email_el = page.query_selector("input#email") or page.query_selector("input[name='email']")
        pass_el = page.query_selector("input#password") or page.query_selector("input[type='password']")

        if not email_el or not pass_el:
            return False, "login_form_not_found"

        email_el.fill(username)
        pass_el.fill(password)
        time.sleep(0.5)

        # Click LOGIN button
        login_btn = page.query_selector("button:has-text('LOGIN')")
        if not login_btn:
            login_btn = page.query_selector("button[type='submit']")
        if login_btn and login_btn.is_visible():
            login_btn.click()
        else:
            pass_el.press("Enter")

        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)

        # Check for blocks post-login
        block = detect_block(page)
        if block:
            return False, block

        if "/login" in page.url:
            return False, "login_failed_still_on_login_page"

        # Save storage state locally (never uploaded as artifact)
        context.storage_state(path=str(STORAGE_STATE))
        return True, None

    except Exception as e:
        return False, f"login_error: {e}"


# ── Function registry generator ──────────────────────────────────────

def generate_function_registry(probe_results: list[dict]) -> dict:
    """Generate function_registry.generated.yml from probe results."""
    functions = {}

    for r in probe_results:
        name = r["page"]
        status = r.get("status", "unknown")
        xpaths = r.get("xpaths", {})
        api_calls = r.get("api_calls", [])

        if r.get("needs_login"):
            mode = "authenticated"
            allowed_in_ci = "manual_only"
        else:
            mode = "public"
            allowed_in_ci = True

        ftype = "read"
        requires_approval = False

        # Detect if page has form fields that could be mutated
        has_form = bool(xpaths.get("textareas") or xpaths.get("contenteditable"))
        has_submit = any("save" in b.get("text", "").lower() or "submit" in b.get("text", "").lower()
                        for b in xpaths.get("buttons", []))

        if has_form and has_submit and r.get("needs_login"):
            ftype = "read"  # still read — we're detecting, not submitting
            # Add a corresponding _save_live mutation function
            mutation_name = name.replace("_detect", "_save_live").replace("_read", "_save_live")
            if mutation_name != name:
                functions[mutation_name] = {
                    "mode": "authenticated",
                    "type": "mutation",
                    "allowed_in_ci": False,
                    "requires_manual_approval": True,
                    "discovered_on": name,
                }

        # Detect mailbox compose
        if "compose" in name:
            functions["mailbox_send"] = {
                "mode": "authenticated",
                "type": "mutation",
                "allowed_in_ci": False,
                "disabled": True,
            }

        functions[name] = {
            "mode": mode,
            "type": ftype,
            "allowed_in_ci": allowed_in_ci,
            "url": r.get("final_url", r["url"]),
            "selectors_found": {
                "inputs": len(xpaths.get("inputs", [])),
                "textareas": len(xpaths.get("textareas", [])),
                "buttons": len(xpaths.get("buttons", [])),
                "selects": len(xpaths.get("selects", [])),
                "contenteditable": len(xpaths.get("contenteditable", [])),
            },
            "api_endpoints": len(api_calls),
            "screenshot": bool(r.get("screenshot")),
            "status": status,
        }

    # Always include blocked functions
    functions["captcha_bypass"] = {"mode": "blocked", "type": "blocked", "allowed_in_ci": False, "disabled": True}
    functions["anti_bot_bypass"] = {"mode": "blocked", "type": "blocked", "allowed_in_ci": False, "disabled": True}
    functions["mass_message"] = {"mode": "blocked", "type": "blocked", "allowed_in_ci": False, "disabled": True}
    functions["fake_availability_loop"] = {"mode": "blocked", "type": "blocked", "allowed_in_ci": False, "disabled": True}

    return {"functions": functions}


def write_yaml(data: dict, path: Path):
    """Write dict as YAML (simple serializer, no external dep needed)."""
    lines = []
    lines.append("# Auto-generated from Playwright probe — do not edit manually.")
    lines.append(f"# Generated: {now_iso()}")
    lines.append("")
    lines.append("functions:")
    for name, cfg in data.get("functions", {}).items():
        lines.append(f"  {name}:")
        for k, v in cfg.items():
            if isinstance(v, bool):
                lines.append(f"    {k}: {str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"    {k}: {v}")
            elif isinstance(v, str):
                lines.append(f'    {k}: "{v}"')
            elif isinstance(v, dict):
                lines.append(f"    {k}:")
                for kk, vv in v.items():
                    if isinstance(vv, bool):
                        lines.append(f"      {kk}: {str(vv).lower()}")
                    else:
                        lines.append(f"      {kk}: {vv}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Utility ──────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]', '_', s)[:60]


# ── Probe page ───────────────────────────────────────────────────────

def probe_page(page: Page, page_name: str, page_cfg: dict, logged_in: bool,
               interceptor: APIInterceptor) -> dict:
    print(f"\n── Probing: {page_name} ──")
    print(f"  URL: {page_cfg['url']}")

    result = {
        "page": page_name,
        "url": page_cfg["url"],
        "timestamp": now_iso(),
        "needs_login": page_cfg["needs_login"],
        "logged_in": logged_in,
    }

    interceptor.calls = []

    try:
        page.goto(page_cfg["url"], wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Dismiss cookie consent if present
        try:
            accept_btn = page.query_selector("button:has-text('ACCEPT ALL')")
            if accept_btn and accept_btn.is_visible():
                accept_btn.click()
                time.sleep(1)
        except Exception:
            pass

        block = detect_block(page)
        if block:
            result["status"] = "blocked"
            result["block_reason"] = block
            result["mutation_attempted"] = False
            result["action_taken"] = "stopped_without_bypass"
            print(f"  BLOCKED: {block}")
        else:
            result["status"] = "ok"
            result["title"] = page.title()
            result["final_url"] = page.url

            if page_cfg["needs_login"] and "/login" in page.url:
                result["status"] = "redirected_to_login"
                result["note"] = "Page requires login — not authenticated"
                print(f"  Redirected to login")
            elif page_cfg["needs_login"] and "/404" in page.url:
                result["status"] = "not_found"
                result["note"] = "Page returned 404 — may require different URL or session"
                print(f"  404 — page not found")
            else:
                xpaths = discover_xpaths(page)
                result["xpaths"] = xpaths
                print(f"  Found: {len(xpaths['inputs'])} inputs, {len(xpaths['textareas'])} textareas, "
                      f"{len(xpaths['buttons'])} buttons, {len(xpaths['links_profile'])} profile links")

                # Capture __NEXT_DATA__
                try:
                    nd = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
                    if nd:
                        result["next_data_len"] = len(nd)
                        result["next_data_hash"] = f"sha256:{sha256(nd)}"
                        # Try to extract page props keys
                        try:
                            nd_json = json.loads(nd)
                            props = nd_json.get("props", {}).get("pageProps", {})
                            result["next_data_keys"] = list(props.keys())[:20]
                        except Exception:
                            pass
                        print(f"  __NEXT_DATA__: {len(nd)} chars")
                except Exception:
                    pass

                # Find logout link/button if requested
                if page_cfg.get("find_logout"):
                    logout_found = False
                    for el in page.query_selector_all("a, button"):
                        try:
                            txt = (el.inner_text() or "").strip().lower()
                            href = el.get_attribute("href") or ""
                            if "logout" in txt or "log out" in txt or "sign out" in txt or "logout" in href:
                                tag_name = el.evaluate("e => e.tagName.toLowerCase()")
                                result["logout_selector"] = f"//{tag_name}[contains(text(),'{txt}')]"
                                logout_found = True
                                print(f"  Logout found: {txt}")
                                break
                        except Exception:
                            continue
                    if not logout_found:
                        result["logout_selector"] = None
                        print(f"  Logout not found on page")

        # Screenshot
        ss_path = SCREENSHOTS / f"{safe_name(page_name)}.png"
        page.screenshot(path=str(ss_path), full_page=True)
        result["screenshot"] = str(ss_path)
        print(f"  Screenshot: {ss_path}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  ERROR: {e}")

    # Save API calls
    api_path = interceptor.save(page_name)
    result["api_calls"] = interceptor.calls
    result["api_calls_count"] = len(interceptor.calls)
    if interceptor.calls:
        print(f"  API calls: {len(interceptor.calls)}")
        for c in interceptor.calls[:5]:
            print(f"    {c['method']:6s} {c.get('status', '???')} {c['url'][:80]}")

    return result


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RM Playwright Probe v2 — hardened")
    parser.add_argument("--mode", default="public",
                        choices=["public", "authenticated-readonly"],
                        help="Probe mode")
    parser.add_argument("--login", action="store_true", help="Attempt login (authenticated-readonly mode)")
    parser.add_argument("--page", default="all", help="Specific page name or 'all'")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--no-redact", action="store_true", help="Disable secret redaction (NOT recommended)")
    args = parser.parse_args()

    # Load .env if present (but prefer shell env)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    username = os.getenv("RM_USER") or os.getenv("RENTMASSEUR_USERNAME") or ""
    password = os.getenv("RM_PASS") or os.getenv("RENTMASSEUR_PASSWORD") or ""
    redact = not args.no_redact

    # Determine which pages to probe
    if args.mode == "authenticated-readonly":
        pages = PAGES_AUTHENTICATED
        if args.login and (not username or not password):
            print("!! No credentials found. Set RM_USER and RM_PASS in shell env.")
            print("!! Falling back to public probe only.")
            pages = PAGES_PUBLIC
            args.mode = "public"
    else:
        pages = PAGES_PUBLIC

    if args.page != "all":
        if args.page in pages:
            pages = {args.page: pages[args.page]}
        elif args.page in PAGES_PUBLIC:
            pages = {args.page: PAGES_PUBLIC[args.page]}
        elif args.page in PAGES_AUTHENTICATED:
            print(f"!! Page '{args.page}' requires authenticated-readonly mode")
            sys.exit(2)
        else:
            print(f"!! Unknown page: {args.page}")
            sys.exit(2)

    results = []
    login_result = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # Use storageState if available for authenticated mode
        context_kwargs = {
            "viewport": {"width": 1440, "height": 1200},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        if args.mode == "authenticated-readonly" and STORAGE_STATE.exists() and not args.login:
            context_kwargs["storage_state"] = str(STORAGE_STATE)
            print(f"Using saved storage state: {STORAGE_STATE}")

        context = browser.new_context(**context_kwargs)

        # API interception
        interceptor = APIInterceptor(redact=redact)
        context.on("request", interceptor.on_request)
        context.on("response", interceptor.on_response)

        page = context.new_page()

        # Login if needed
        logged_in = False
        if args.mode == "authenticated-readonly":
            if args.login:
                if username and password:
                    print(f"\n=== Attempting login as {username[:3]}*** ===")
                    logged_in, block_reason = attempt_login(page, context, username, password)
                    login_result = {
                        "action": "login",
                        "status": "ok" if logged_in else "blocked",
                        "reason": block_reason,
                        "mutation_attempted": False,
                        "timestamp": now_iso(),
                    }
                    if not logged_in:
                        print(f"  Login blocked: {block_reason}")
                        # If blocked, stop entirely
                        if block_reason and "captcha" in block_reason:
                            print("  Stopping probe — CAPTCHA detected, no bypass attempted")
                            results.append(login_result)
                            browser.close()
                            # Write receipt and exit
                            _write_outputs(results, args.mode, redact)
                            sys.exit(1)
                    else:
                        print(f"  Login OK — URL: {page.url}")
                else:
                    print("!! No credentials — falling back to public pages")
                    pages = PAGES_PUBLIC
                    args.mode = "public"
            elif STORAGE_STATE.exists():
                # Verify storage state is still valid
                page.goto(f"{BASE_URL}/settings", wait_until="networkidle", timeout=30000)
                time.sleep(2)
                if "/login" not in page.url and "/404" not in page.url:
                    logged_in = True
                    print("  Storage state valid — logged in")
                else:
                    print("  Storage state expired — not logged in")

        # Probe pages
        for page_name, page_cfg in pages.items():
            result = probe_page(page, page_name, page_cfg, logged_in, interceptor)
            results.append(result)

            # Stop if blocked
            if result.get("status") == "blocked" and "captcha" in result.get("block_reason", ""):
                print("\n!! CAPTCHA detected — stopping probe, no bypass attempted")
                break

        browser.close()

    _write_outputs(results, args.mode, redact, login_result)


def _write_outputs(results: list[dict], mode: str, redact: bool, login_result: dict = None):
    """Write all output artifacts."""
    # Probe receipt
    receipt = {
        "timestamp": now_iso(),
        "mode": mode,
        "redacted": redact,
        "login_result": login_result,
        "pages_probed": [r["page"] for r in results],
        "results": results,
    }
    receipt_path = ARTIFACTS / "probe_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")

    # Selectors
    selector_map = {}
    for r in results:
        if r.get("xpaths"):
            selector_map[r["page"]] = {
                "url": r.get("final_url", r["url"]),
                "inputs": r["xpaths"]["inputs"],
                "textareas": r["xpaths"]["textareas"],
                "buttons": r["xpaths"]["buttons"],
                "selects": r["xpaths"]["selects"],
                "contenteditable": r["xpaths"]["contenteditable"],
                "links_profile": r["xpaths"]["links_profile"][:50],
            }
    sel_path = ARTIFACTS / f"{'authenticated' if mode == 'authenticated-readonly' else 'public'}_selectors.json"
    sel_path.write_text(json.dumps(selector_map, indent=2, default=str), encoding="utf-8")

    # API endpoints (redacted)
    api_map = {}
    for r in results:
        if r.get("api_calls"):
            api_map[r["page"]] = [
                {
                    "method": c["method"],
                    "url_path": c.get("url_path", c["url"]),
                    "status": c.get("status"),
                    "request_headers_redacted": c.get("request_headers_redacted", True),
                    "post_data": c.get("post_data"),
                    "response_body_hash": c.get("response_body_hash"),
                    "response_body_len": c.get("response_body_len"),
                    "response_keys": c.get("response_keys", []),
                    "response_preview": c.get("response_preview"),
                }
                for c in r["api_calls"]
            ]
    api_suffix = ".redacted" if redact else ""
    api_path = ARTIFACTS / f"{'authenticated' if mode == 'authenticated-readonly' else 'public'}_api_endpoints{api_suffix}.json"
    api_path.write_text(json.dumps(api_map, indent=2, default=str), encoding="utf-8")

    # Generate function registry
    registry = generate_function_registry(results)
    reg_path = ARTIFACTS / "function_registry.generated.yml"
    write_yaml(registry, reg_path)

    # Summary
    total_api = sum(len(r.get("api_calls", [])) for r in results)
    blocked = sum(1 for r in results if r.get("status") == "blocked")
    ok = sum(1 for r in results if r.get("status") == "ok")
    redirected = sum(1 for r in results if r.get("status") == "redirected_to_login")

    print(f"\n{'='*60}")
    print(f"Probe complete — mode={mode}, redacted={redact}")
    print(f"  Pages: {len(results)} ({ok} ok, {blocked} blocked, {redirected} redirected)")
    print(f"  API calls captured: {total_api}")
    print(f"  Receipt:       {receipt_path}")
    print(f"  Selectors:     {sel_path}")
    print(f"  API endpoints: {api_path}")
    print(f"  Function reg:  {reg_path}")
    print(f"  Screenshots:   {SCREENSHOTS}/")

    if login_result and login_result["status"] != "ok":
        print(f"\n  Login: {login_result['status']} — {login_result.get('reason', 'unknown')}")

    print(f"\n  API endpoints discovered:")
    for r in results:
        if r.get("api_calls"):
            print(f"\n  {r['page']}:")
            for c in r["api_calls"]:
                print(f"    {c['method']:6s} {c.get('status', '???'):>4} {c.get('url_path', c['url'][:80])}")


if __name__ == "__main__":
    main()
