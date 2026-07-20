"""SHA-chained JSONL receipt ledger for tamper-evident audit trail."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional


class ReceiptLedger:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "ledger.jsonl"
        self.entries: list[dict] = []
        if self.ledger_path.exists():
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self.entries.append(json.loads(line))
                    except Exception:
                        pass

    def _prev_hash(self) -> str:
        return self.entries[-1].get("hash", "0" * 64) if self.entries else "0" * 64

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def write(self, action: str, status: str, data: dict) -> Path:
        payload = {
            "index": len(self.entries),
            "ts": int(time.time()),
            "prev_hash": self._prev_hash(),
            "action": action,
            "status": status,
            "data": data,
        }
        body = json.dumps(
            {k: v for k, v in payload.items() if k != "hash"},
            sort_keys=True,
            default=str,
        )
        payload["hash"] = self._sha256(body)
        self.entries.append(payload)

        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

        safe_action = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in action)[:60]
        receipt_path = self.root / f"{payload['index']:05d}_{safe_action}_{status}.json"
        receipt_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return receipt_path

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
            if self._sha256(body) != entry.get("hash"):
                return False
            prev = entry["hash"]
        return True
