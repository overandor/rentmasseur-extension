"""Approval gate — blocks live mutations unless manually approved with token + candidate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


BLOCKED_IN_CI = {
    "bio_apply_live",
    "availability_set_live",
    "send_message",
    "mass_message",
    "profile_scrape",
    "captcha_bypass",
    "anti_bot_bypass",
    "fake_availability_loop",
}


class ApprovalGate:
    def __init__(self, mode: str):
        self.mode = mode

    def is_blocked(self, function_name: str, function_config: dict) -> Optional[str]:
        ftype = function_config.get("type", "")
        allowed_in_ci = function_config.get("allowed_in_ci", False)
        requires_approval = function_config.get("requires_manual_approval", False)

        if function_name in BLOCKED_IN_CI:
            if self.mode != "approved_mutation":
                return "live_mutation_blocked_outside_approved_mutation_mode"

        if ftype == "mutation" and self.mode != "approved_mutation":
            return "mutation_requires_approved_mutation_mode"

        if not allowed_in_ci and self.mode in ("proof", "live_readonly"):
            return "function_not_allowed_in_ci_registry"

        if requires_approval and self.mode != "approved_mutation":
            return "function_requires_manual_approval"

        return None

    def verify_approval_token(self, token: str) -> bool:
        expected = os.getenv("ADMIN_TOKEN") or os.getenv("RM_APPROVAL_TOKEN") or ""
        return bool(expected) and token == expected

    def load_candidate(self, candidate_file: str) -> Optional[dict]:
        path = Path(candidate_file)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def check_selector_proof(self, action: str, proof_dir: str = "debug") -> bool:
        proof_path = Path(proof_dir) / f"{action}_selectors.json"
        return proof_path.exists()
