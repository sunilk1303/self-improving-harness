"""Control-domain tier derivation — tier is DERIVED from what a change
touches, never trusted from the proposer's declaration.

This is the fix for the security red-team's top finding (docs/08 #4): if the
policy layer keys off the declared change_type, the tier system is
self-attestation and a T2 payload labeled "T0 few-shot" auto-merges through
the lowest gate. Here the declared tier is a claim to be cross-checked; a
mismatch is a fabrication event, not a warning.

Severity order: DENIED > T3 > T2 > T1 > T0. The most severe rule that fires
wins; anything no rule recognizes default-denies into T2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .change import CandidateChange

TIER_ORDER = ["T0", "T1", "T2", "T3", "DENIED"]

# Paths the improvement loop must never touch — no write path should exist
# (structural impossibility); a candidate claiming them is rejected outright.
_DENIED_PREFIXES = (
    "harness/gate/", "harness/evalkit/", "harness/ledger",
    "data/golden/", "tests/",
    "manifests/labels.yaml",   # deploys are the controller's job, not a change
    ".github/", "policy/",
)

_PATH_RULES: list[tuple[str, str, str]] = [
    # (path prefix, tier, reason)
    ("harness/", "T3", "agent code"),
    ("scripts/", "T3", "agent code"),
    ("pyproject.toml", "T3", "dependency/build change"),
    ("artifacts/vqr/", "T2", "verified-query activation surface"),
    ("artifacts/semantic/", "T2", "metric definition surface"),
    ("artifacts/playbook/", "T0", "playbook delta"),
    ("artifacts/fewshots/", "T0", "retrieval few-shot"),
    ("manifests/", "T2", "manifest content change"),
]

_MANIFEST_KEY_RULES: list[tuple[str, str, str]] = [
    ("agent.nl2sql", "T3", "model/provider change"),
    ("data.", "T3", "data source scope change"),
    ("eval.", "DENIED", "eval configuration is outside the improvement surface"),
    ("agent.vqr_version", "T2", "verified-query activation"),
    ("agent.", "T1", "agent parameter change"),
]


@dataclass
class TierVerdict:
    derived_tier: str
    reasons: list[str] = field(default_factory=list)

    @property
    def denied(self) -> bool:
        return self.derived_tier == "DENIED"


def _more_severe(a: str, b: str) -> str:
    return a if TIER_ORDER.index(a) >= TIER_ORDER.index(b) else b


def derive_tier(change: CandidateChange) -> TierVerdict:
    tier = "T0"
    reasons: list[str] = []

    for path in sorted(change.files):
        norm = path.replace("\\", "/")
        if any(norm.startswith(p) for p in _DENIED_PREFIXES):
            tier = "DENIED"
            reasons.append(f"{path}: outside the improvement surface")
            continue
        for prefix, ptier, why in _PATH_RULES:
            if norm.startswith(prefix):
                tier = _more_severe(tier, ptier)
                reasons.append(f"{path}: {why} -> {ptier}")
                break
        else:
            tier = _more_severe(tier, "T2")
            reasons.append(f"{path}: unrecognized path -> default-deny T2")

    for key in sorted(change.manifest_diff):
        for prefix, ktier, why in _MANIFEST_KEY_RULES:
            if key.startswith(prefix):
                tier = _more_severe(tier, ktier)
                reasons.append(f"manifest:{key}: {why} -> {ktier}")
                break
        else:
            tier = _more_severe(tier, "T2")
            reasons.append(f"manifest:{key}: unrecognized key -> default-deny T2")

    if not change.files and not change.manifest_diff:
        tier = "DENIED"
        reasons.append("empty change: nothing to review")

    return TierVerdict(tier, reasons)
