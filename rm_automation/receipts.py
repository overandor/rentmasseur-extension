"""SHA-chained JSONL receipt ledger for tamper-evident audit trail."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


RECEIPT_DIR = Path("receipts")
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = RECEIPT_DIR / "ledger.jsonl"


@dataclass
class Receipt:
    index: int
    timestamp: str
    prev_hash: str
    action: str
    lane: str
    risk: str
    ok: bool
    status: str
    url: str = ""
    screenshot: str = ""
    html_snapshot: str = ""
    data: Optional[dict] = None
    error: Optional[str] = None
    blocked_reason: Optional[str] = None
    hash: str = ""


class ReceiptLedger:
    def __init__(self, path: Path = LEDGER_PATH):
        self.path = path
        self.entries: list[dict] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self.entries.append(json.loads(line))
                    except Exception:
                        pass

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _safe_name(self, s: str) -> str:
        return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)[:80]

    def add(self, payload: dict) -> str:
        prev_hash = self.entries[-1].get("hash", "0" * 64) if self.entries else "0" * 64
        entry = {
            "index": len(self.entries),
            "timestamp": self._now_iso(),
            "prev_hash": prev_hash,
            **payload,
        }
        body = json.dumps(
            {k: v for k, v in entry.items() if k != "hash"},
            sort_keys=True,
            default=str,
        )
        entry["hash"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        receipt_path = RECEIPT_DIR / f"{entry['index']:05d}_{self._safe_name(payload.get('action', 'action'))}.json"
        receipt_path.write_text(
            json.dumps(entry, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return str(receipt_path)

    def verify(self) -> bool:
        prev = "0" * 64
        for entry in self.entries:
            if entry.get("prev_hash") != prev:
                return False
            body = json.dumps(
                {k: v for k, v in entry.items() if k != "hash"},
                sort_keys=True,
                default=str,
            )
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != entry.get("hash"):
                return False
            prev = entry["hash"]
        return True
