"""S1 static gate — the cheap, deterministic checks every candidate faces first.

Checks (each a typed result; any FAIL kills the candidate at ~$0 cost):
  1. tier-derivation cross-check — declared vs derived mismatch is a
     FABRICATION event (quarantine-grade), not a warning.
  2. secret/credential scan over all proposed content — a secret that reaches
     the ledger or Git is permanent; prevention must be upstream.
  3. artifact validation — proposed VQR versions must parse, every entry's SQL
     must pass the read-only allowlist, patterns must compile, placeholders
     must match params.
  4. size caps — oversized diffs are rejected as unreviewable (the complexity
     tax's crude ancestor; the full tax arrives with E1+).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import yaml

from .change import CandidateChange
from .tiers import TierVerdict, derive_tier

MAX_TOTAL_BYTES = 100_000
MAX_VQR_ENTRIES_PER_CHANGE = 5

_SECRET_PATTERNS = [
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")),
    ("openai/api key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("azure/generic key assignment", re.compile(
        r"(?i)\b(api[_-]?key|password|secret|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9+/_-]{16,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("connection string credential", re.compile(r"(?i)://[^/\s:]+:[^@\s]+@")),
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GateResult:
    change_id: str
    tier: TierVerdict
    checks: list[CheckResult] = field(default_factory=list)
    fabrication: bool = False

    @property
    def passed(self) -> bool:
        return (not self.tier.denied and not self.fabrication
                and all(c.passed for c in self.checks))


def _scan_secrets(change: CandidateChange) -> list[CheckResult]:
    results = []
    for path, content in change.files.items():
        hits = [name for name, pat in _SECRET_PATTERNS if pat.search(str(content))]
        if hits:
            results.append(CheckResult(
                "secret_scan", False, f"{path}: matched {', '.join(hits)}"))
    if not results:
        results.append(CheckResult("secret_scan", True))
    return results


def _validate_vqr_files(change: CandidateChange) -> list[CheckResult]:
    from ..agent.llm import validate_sql

    results = []
    for path, content in change.files.items():
        if not path.replace("\\", "/").startswith("artifacts/vqr/"):
            continue
        try:
            doc = yaml.safe_load(io.StringIO(str(content)))
            entries = doc.get("entries", [])
            if not isinstance(entries, list):
                raise ValueError("entries must be a list")
            if len(entries) == 0:
                raise ValueError("empty VQR artifact")
            new_ids = [e["id"] for e in entries]
            if len(new_ids) != len(set(new_ids)):
                raise ValueError("duplicate entry ids")
            for e in entries:
                sql = validate_sql(e["sql"])
                pat = re.compile(e["question_pattern"], re.I)
                params = list(e.get("params", []))
                if set(params) - set(pat.groupindex):
                    raise ValueError(f"{e['id']}: params not captured by pattern")
                if sql.count("?") != len(params):
                    raise ValueError(f"{e['id']}: placeholder/param count mismatch")
        except Exception as exc:
            results.append(CheckResult("vqr_validation", False, f"{path}: {exc}"))
        else:
            results.append(CheckResult("vqr_validation", True, path))
    return results


def run_static_gate(change: CandidateChange, ledger=None) -> GateResult:
    tier = derive_tier(change)
    result = GateResult(change.change_id, tier)

    declared = change.declared_tier.upper()
    if declared != tier.derived_tier:
        result.fabrication = True
        result.checks.append(CheckResult(
            "tier_crosscheck", False,
            f"declared {declared} but derived {tier.derived_tier} "
            f"({'; '.join(tier.reasons)}) — fabrication event"))
    else:
        result.checks.append(CheckResult("tier_crosscheck", True, tier.derived_tier))

    result.checks.extend(_scan_secrets(change))
    result.checks.extend(_validate_vqr_files(change))

    total = sum(len(str(c)) for c in change.files.values())
    result.checks.append(CheckResult(
        "size_cap", total <= MAX_TOTAL_BYTES,
        f"{total} bytes (cap {MAX_TOTAL_BYTES})"))

    if ledger is not None:
        ledger.append(
            "gate_result",
            {"stage": "S1", "change_id": change.change_id,
             "declared_tier": declared, "derived_tier": tier.derived_tier,
             "fabrication": result.fabrication, "passed": result.passed,
             "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail}
                        for c in result.checks]},
            actor="gate")
    return result
