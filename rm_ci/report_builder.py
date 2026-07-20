"""Report builder — generates CI artifact summary from receipts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import list


def build_report(receipts_dir: Path, artifacts_dir: Path, mode: str, functions_run: list[str]) -> Path:
    receipts = []
    ledger_path = receipts_dir / "ledger.jsonl"
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    receipts.append(json.loads(line))
                except Exception:
                    pass

    passed = sum(1 for r in receipts if r.get("status") == "pass")
    failed = sum(1 for r in receipts if r.get("status") == "fail")
    blocked = sum(1 for r in receipts if r.get("status") == "blocked")
    skipped = sum(1 for r in receipts if r.get("status") == "skipped")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "functions_requested": functions_run,
        "summary": {
            "total": len(receipts),
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "skipped": skipped,
        },
        "receipts": receipts,
    }

    reports_dir = artifacts_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"ci_report_{int(datetime.now(timezone.utc).timestamp())}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Also write latest.json for easy access
    (reports_dir / "latest.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )

    return report_path
