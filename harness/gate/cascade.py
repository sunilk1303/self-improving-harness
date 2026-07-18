"""The staged gate cascade — S1 -> S2 -> S3 -> S4, cheap to expensive.

A candidate stops at the first stage it fails, so hacks die cheap (the ~90%
rejection is mostly at S1/S2 at ~$0) and only genuine contenders reach the
paid LLM eval stages. The expensive eval is injected as `eval_fn(manifest,
slice_name) -> report` so the orchestration is unit-testable with mock reports
while production passes an LLM-backed evaluator.

Returns a CascadeResult with every stage's outcome and, for a T0/T1/T2
candidate that passes, the eval deltas — the raw material of an
ImprovementRecord (docs/05). Every stage is ledger-logged by its own runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .change import CandidateChange
from .eval_gate import GateDecision, public_gate
from .sandbox import run_sandbox_gate
from .static_checks import run_static_gate

STAGES = ["S1", "S2", "S3", "S4"]


@dataclass
class CascadeResult:
    change_id: str
    accepted: bool
    reached: str                       # last stage entered
    failed_at: str | None = None
    derived_tier: str = ""
    fabrication: bool = False
    public: GateDecision | None = None
    private_accept: bool | None = None
    notes: list = field(default_factory=list)


def _apply(manifest: dict, diff: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in manifest.items()}
    for dotted, value in diff.items():
        node = out
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


def run_cascade(change: CandidateChange, base_manifest: dict, snapshot,
                workdir, eval_fn=None, ledger=None,
                run_eval_stages: bool = True) -> CascadeResult:
    result = CascadeResult(change.change_id, accepted=False, reached="S1")

    # S1 — static
    s1 = run_static_gate(change, ledger=ledger)
    result.derived_tier = s1.tier.derived_tier
    result.fabrication = s1.fabrication
    if not s1.passed:
        result.failed_at = "S1"
        result.notes.append(f"S1: {[c.detail for c in s1.checks if not c.passed]}")
        return result

    # S2 — sandbox
    result.reached = "S2"
    s2 = run_sandbox_gate(change, base_manifest, workdir=workdir,
                          snapshot=snapshot, ledger=ledger)
    if not s2.passed:
        result.failed_at = "S2"
        result.notes.append(f"S2: {s2.detail}")
        return result

    if not run_eval_stages or eval_fn is None:
        result.notes.append("eval stages skipped (no eval_fn)")
        result.accepted = True  # passed all executed stages
        return result

    cand_manifest = _apply(base_manifest, change.manifest_diff)

    # S3 — public gate
    result.reached = "S3"
    inc_pub = eval_fn(base_manifest, "public")
    cand_pub = eval_fn(cand_manifest, "public")
    decision = public_gate(inc_pub, cand_pub)
    result.public = decision
    if ledger is not None:
        ledger.append("gate_result",
                      {"stage": "S3", "change_id": change.change_id,
                       "accepted": decision.accepted, "mean_delta": decision.mean_delta,
                       "ci": [decision.ci_low, decision.ci_high],
                       "regressing_strata": decision.regressing_strata,
                       "reason": decision.reason}, actor="gate")
    if not decision.accepted:
        result.failed_at = "S3"
        result.notes.append(f"S3: {decision.reason}")
        return result

    # S4 — private gate (accept/reject bit only)
    result.reached = "S4"
    inc_priv = eval_fn(base_manifest, "private")
    cand_priv = eval_fn(cand_manifest, "private")
    private_ok = public_gate(inc_priv, cand_priv).accepted
    result.private_accept = private_ok
    if ledger is not None:
        ledger.append("gate_result",
                      {"stage": "S4", "change_id": change.change_id,
                       "accepted": private_ok}, actor="gate")
    if not private_ok:
        result.failed_at = "S4"
        result.notes.append("S4: private slice did not confirm")
        return result

    result.accepted = True
    return result
