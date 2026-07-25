#!/usr/bin/env python3
"""
Fingerprint utility — SHA-256 hash-chained receipts for pipeline replication.

Each receipt gets:
  fingerprint:   SHA-256 of canonical JSON (sorted keys, no whitespace)
  prev_fingerprint:  fingerprint of the previous receipt in the chain (or None for genesis)
  chain_index:   sequential integer (0, 1, 2, ...)

To replicate: re-run the pipeline with the same inputs and verify fingerprints match.
To verify integrity: recompute SHA-256 from canonical JSON and compare.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

RECEIPTS_DIR = Path(__file__).parent / "receipts"
CHAIN_FILE = RECEIPTS_DIR / "chain_head.json"


def canonical_json(obj: Any) -> str:
    """Serialize to canonical JSON: sorted keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_fingerprint(obj: Any) -> str:
    """Compute SHA-256 fingerprint of an object's canonical JSON."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def get_chain_head() -> Optional[Dict]:
    """Load the current chain head (last receipt in the chain)."""
    if CHAIN_FILE.exists():
        with CHAIN_FILE.open() as f:
            return json.load(f)
    return None


def update_chain_head(receipt: Dict) -> None:
    """Update the chain head to point to the latest receipt."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    with CHAIN_FILE.open("w") as f:
        json.dump(receipt, f, indent=2)


def stamp_receipt(receipt: Dict) -> Dict:
    """
    Add fingerprint, prev_fingerprint, and chain_index to a receipt.
    Returns the stamped receipt (mutates in place and returns it).
    """
    head = get_chain_head()
    prev_fp = head["fingerprint"] if head else None
    chain_index = (head["chain_index"] + 1) if head else 0

    receipt["prev_fingerprint"] = prev_fp
    receipt["chain_index"] = chain_index
    receipt["fingerprint"] = sha256_fingerprint(receipt)

    update_chain_head(receipt)
    return receipt


def verify_receipt(receipt: Dict) -> bool:
    """
    Verify a receipt's fingerprint matches its content.
    Does NOT verify chain linkage — use verify_chain for that.
    """
    if "fingerprint" not in receipt:
        return False
    expected = receipt.pop("fingerprint")
    computed = sha256_fingerprint(receipt)
    receipt["fingerprint"] = expected  # restore
    return expected == computed


def verify_chain(receipts: list) -> Dict:
    """
    Verify a list of receipts forms a valid hash chain.
    Returns {"valid": bool, "checked": int, "errors": [str]}.
    """
    errors = []
    prev_fp = None
    for i, r in enumerate(receipts):
        if r.get("chain_index") != i:
            errors.append(f"chain_index mismatch at {i}: got {r.get('chain_index')}")
        if r.get("prev_fingerprint") != prev_fp:
            errors.append(f"prev_fingerprint mismatch at index {i}")
        if not verify_receipt(r):
            errors.append(f"fingerprint mismatch at index {i}")
        prev_fp = r.get("fingerprint")
    return {"valid": len(errors) == 0, "checked": len(receipts), "errors": errors}


def load_all_receipts() -> list:
    """Load all receipt JSON files from receipts/ dir, sorted by chain_index."""
    receipts = []
    for p in sorted(RECEIPTS_DIR.glob("*.json")):
        if p.name == "chain_head.json":
            continue
        with p.open() as f:
            try:
                r = json.load(f)
                if "fingerprint" in r:
                    receipts.append(r)
            except json.JSONDecodeError:
                continue
    receipts.sort(key=lambda r: r.get("chain_index", 0))
    return receipts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Receipt fingerprint utilities")
    parser.add_argument("--verify", action="store_true", help="Verify the receipt chain")
    parser.add_argument("--show", action="store_true", help="Show all receipts with fingerprints")
    args = parser.parse_args()

    if args.verify:
        receipts = load_all_receipts()
        result = verify_chain(receipts)
        print(json.dumps(result, indent=2))
        if result["valid"]:
            print(f"\n✅ Chain valid: {result['checked']} receipts verified")
        else:
            print(f"\n❌ Chain INVALID: {len(result['errors'])} errors")
            for e in result["errors"]:
                print(f"  - {e}")

    if args.show:
        receipts = load_all_receipts()
        for r in receipts:
            print(f"[{r.get('chain_index', '?')}] {r.get('fingerprint', '?')[:16]}  "
                  f"{r.get('action', '?')}  {r.get('timestamp', '?')}")
