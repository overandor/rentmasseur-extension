"""Function registry — all RM functions declared with risk level and lane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict


LANE_AUDIT = "audit"
LANE_DRY_RUN = "dry_run"
LANE_EXECUTE_APPROVED = "execute_approved"
LANE_BLOCKED = "blocked"


@dataclass
class FunctionSpec:
    name: str
    lane: str
    risk: str
    description: str


RM_FUNCTIONS: Dict[str, FunctionSpec] = {
    # --- audit (read-only, safe on GitHub Actions) ---
    "login_check": FunctionSpec("login_check", LANE_AUDIT, "low", "Login with first-party credentials, verify session, capture screenshot."),
    "dashboard_snapshot": FunctionSpec("dashboard_snapshot", LANE_AUDIT, "low", "Read dashboard/settings page, capture signals + screenshot."),
    "availability_snapshot": FunctionSpec("availability_snapshot", LANE_AUDIT, "low", "Read availability screen, capture state + screenshot."),
    "profile_snapshot": FunctionSpec("profile_snapshot", LANE_AUDIT, "low", "Read public profile page, capture signals + screenshot."),
    "search_rank_read": FunctionSpec("search_rank_read", LANE_AUDIT, "low", "Read public search page, find target rank."),
    "mailbox_read": FunctionSpec("mailbox_read", LANE_AUDIT, "low", "Open mailbox page, capture high-level evidence only."),
    "who_saw_me_snapshot": FunctionSpec("who_saw_me_snapshot", LANE_AUDIT, "medium", "Read Who Saw Me page, capture visitor count + screenshot."),
    "blog_read": FunctionSpec("blog_read", LANE_AUDIT, "low", "Open blogs page, capture evidence."),
    "interview_read": FunctionSpec("interview_read", LANE_AUDIT, "low", "Open interview/settings page, capture evidence."),

    # --- dry_run (form discovery, no submit) ---
    "bio_field_discovery": FunctionSpec("bio_field_discovery", LANE_DRY_RUN, "medium", "Discover editable bio/about form fields, capture selectors, do NOT submit."),
    "availability_form_discovery": FunctionSpec("availability_form_discovery", LANE_DRY_RUN, "medium", "Discover availability toggle/form, capture selectors, do NOT submit."),
    "blog_form_discovery": FunctionSpec("blog_form_discovery", LANE_DRY_RUN, "medium", "Discover blog post form fields, capture selectors, do NOT submit."),
    "interview_form_discovery": FunctionSpec("interview_form_discovery", LANE_DRY_RUN, "medium", "Discover interview form fields, capture selectors, do NOT submit."),

    # --- execute_approved (submit only with token + candidate file) ---
    "apply_approved_bio": FunctionSpec("apply_approved_bio", LANE_EXECUTE_APPROVED, "high", "Submit approved bio text from candidate file. Requires approval token + selector proof."),
    "apply_approved_interview": FunctionSpec("apply_approved_interview", LANE_EXECUTE_APPROVED, "high", "Submit approved interview answers. Requires approval token + selector proof."),
    "apply_approved_blog": FunctionSpec("apply_approved_blog", LANE_EXECUTE_APPROVED, "high", "Submit approved blog post. Requires approval token + selector proof."),
    "set_availability": FunctionSpec("set_availability", LANE_EXECUTE_APPROVED, "high", "Set availability on/off. Requires approval token + selector proof."),

    # --- blocked (never allowed) ---
    "mass_message_users": FunctionSpec("mass_message_users", LANE_BLOCKED, "blocked", "Mass messaging is forbidden per policy."),
    "captcha_bypass": FunctionSpec("captcha_bypass", LANE_BLOCKED, "blocked", "CAPTCHA solving is forbidden per policy."),
    "anti_bot_bypass": FunctionSpec("anti_bot_bypass", LANE_BLOCKED, "blocked", "Anti-bot bypass is forbidden per policy."),
    "fake_availability_loop": FunctionSpec("fake_availability_loop", LANE_BLOCKED, "blocked", "Fake availability loops are forbidden per policy."),
}


def functions_for_lane(lane: str) -> list[str]:
    return [name for name, spec in RM_FUNCTIONS.items() if spec.lane == lane]


def functions_for_mode(mode: str) -> list[str]:
    if mode == "audit":
        return functions_for_lane(LANE_AUDIT)
    elif mode == "dry_run":
        return functions_for_lane(LANE_AUDIT) + functions_for_lane(LANE_DRY_RUN)
    elif mode == "execute_approved":
        return functions_for_lane(LANE_EXECUTE_APPROVED)
    return []


def is_blocked(action: str) -> bool:
    spec = RM_FUNCTIONS.get(action)
    return spec is not None and spec.lane == LANE_BLOCKED


def action_lane(action: str) -> str:
    spec = RM_FUNCTIONS.get(action)
    return spec.lane if spec else ""
