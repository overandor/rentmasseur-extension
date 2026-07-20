"""Policy gate — blocks captcha, mass messaging, unsafe selectors, unapproved actions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BLOCK_REASONS = {
    "captcha_detected": "CAPTCHA or challenge page detected — stopping per policy",
    "crowdsec_detected": "CrowdSec access control detected — stopping per policy",
    "human_verification": "Human verification interstitial detected — stopping per policy",
    "access_forbidden": "Access forbidden detected — stopping per policy",
    "rate_limited": "Rate limit / too many requests detected — stopping per policy",
    "lane_blocked": "Action lane is 'blocked' — this function is forbidden",
    "lane_mismatch": "Requested mode does not cover this action's lane",
    "no_approval_token": "execute_approved requires RM_APPROVAL_TOKEN — not provided",
    "approval_token_mismatch": "Approval token does not match RM_APPROVAL_TOKEN secret",
    "no_candidate_file": "execute_approved requires --candidate-file — not provided",
    "no_selector_proof": "execute_approved requires prior dry-run selector proof — not found",
    "cooldown_active": "Action cooldown has not elapsed — refusing to execute",
    "mass_message_blocked": "Mass messaging is blocked per policy",
    "unsafe_selector": "Selector pattern is in unsafe list — refused",
}


UNSAFE_SELECTOR_PATTERNS = [
    "captcha",
    "g-recaptcha",
    "cf-turnstile",
    "hcaptcha",
    "arkose",
    "funcaptcha",
]


BLOCK_TEXT_NEEDLES = [
    ("captcha", "captcha_detected"),
    ("crowdsec", "crowdsec_detected"),
    ("verify you are human", "human_verification"),
    ("access forbidden", "access_forbidden"),
    ("unusual traffic", "human_verification"),
    ("too many requests", "rate_limited"),
]


@dataclass
class PolicyResult:
    allowed: bool
    reason: Optional[str] = None


def detect_block(page_text: str, current_url: str) -> Optional[str]:
    txt = (page_text or "").lower()
    url = (current_url or "").lower()
    for needle, reason in BLOCK_TEXT_NEEDLES:
        if needle in txt or needle in url:
            return reason
    return None


def check_selector_safety(selector: str) -> bool:
    sel_lower = selector.lower()
    for pattern in UNSAFE_SELECTOR_PATTERNS:
        if pattern in sel_lower:
            return False
    return True


def gate_execute_approved(
    action: str,
    approval_token: str,
    candidate_file: str,
    selector_proof_dir: str = "debug",
) -> PolicyResult:
    if not approval_token:
        return PolicyResult(False, "no_approval_token")
    expected = os.getenv("RM_APPROVAL_TOKEN", "")
    if not expected or approval_token != expected:
        return PolicyResult(False, "approval_token_mismatch")
    if not candidate_file or not Path(candidate_file).exists():
        return PolicyResult(False, "no_candidate_file")
    proof_path = Path(selector_proof_dir) / f"{action}_selectors.json"
    if not proof_path.exists():
        return PolicyResult(False, "no_selector_proof")
    return PolicyResult(True)


def load_candidate(candidate_file: str) -> dict:
    return json.loads(Path(candidate_file).read_text(encoding="utf-8"))
