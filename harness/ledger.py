"""Append-only, SHA-256 hash-chained audit ledger (E0-scale).

One JSONL file; each event commits to the previous event's hash, so any
retroactive edit breaks every subsequent hash. This is the cheap-now,
impossible-to-retrofit spine of the audit design (docs/05). Trust-domain
separation (a logger the agent cannot reach) and WORM anchoring arrive with
the production build — at E0 scale the chain plus `verify()` is the contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS
        last = None
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return 0, GENESIS
        rec = json.loads(last)
        return rec["seq"], rec["hash"]

    def append(self, event_type: str, payload: dict, actor: str = "harness") -> dict:
        seq, prev = self._last_hash()
        record = {
            "seq": seq + 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "prev_hash": prev,
        }
        record["hash"] = hashlib.sha256(
            (prev + _canonical({k: v for k, v in record.items() if k != "prev_hash"}))
            .encode()
        ).hexdigest()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def verify(self) -> tuple[bool, str]:
        """Walk the chain; return (ok, message)."""
        if not self.path.exists():
            return True, "empty ledger"
        prev = GENESIS
        n = 0
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec["prev_hash"] != prev:
                    return False, f"chain broken at line {i}: prev_hash mismatch"
                expected = hashlib.sha256(
                    (prev + _canonical({k: v for k, v in rec.items()
                                        if k not in ("prev_hash", "hash")})).encode()
                ).hexdigest()
                if rec["hash"] != expected:
                    return False, f"chain broken at line {i}: hash mismatch"
                prev = rec["hash"]
                n += 1
        return True, f"{n} events verified"
