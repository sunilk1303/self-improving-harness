"""S3/S4 evaluation gate — the accept/reject decision over eval reports.

Kept pure and separate from eval execution: it takes an incumbent and a
candidate eval report (as produced by evalkit.runner) and applies the
docs/04 gate contract:

  S3 (public): the paired-bootstrap 95% CI of the per-question score delta
  (candidate - incumbent) must exclude zero on the positive side, AND no
  stratum may regress by more than `max_stratum_regression` — the stratified
  guard that catches a change which lifts the pooled average while quietly
  gutting the small hard-question stratum (docs/08 finding #5).

  S4 (private): the same test on the held-out slice, but the caller surfaces
  only the accept/reject bit (Ladder-style) and decrements a leakage budget.

Pairing is by qid; questions absent from either report are dropped with a
recorded count so silent misalignment can't inflate a verdict.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..evalkit.stats import paired_bootstrap

DEFAULT_MAX_STRATUM_REGRESSION = 0.05  # 5 points


@dataclass
class GateDecision:
    accepted: bool
    mean_delta: float
    ci_low: float
    ci_high: float
    n_paired: int
    n_dropped: int
    regressing_strata: list = field(default_factory=list)
    reason: str = ""


def _index(report: dict) -> dict:
    return {r["qid"]: r for r in report["per_question"]}


def public_gate(incumbent: dict, candidate: dict,
                max_stratum_regression: float = DEFAULT_MAX_STRATUM_REGRESSION,
                resamples: int = 1000, seed: int = 7) -> GateDecision:
    inc, cand = _index(incumbent), _index(candidate)
    qids = [q for q in inc if q in cand]
    dropped = (len(inc) - len(qids)) + (len(cand) - len(qids))

    if not qids:
        return GateDecision(False, 0.0, 0.0, 0.0, 0, dropped,
                            reason="no paired questions")

    inc_scores = [inc[q]["score"] for q in qids]
    cand_scores = [cand[q]["score"] for q in qids]
    boot = paired_bootstrap(inc_scores, cand_scores, resamples=resamples, seed=seed)

    # per-stratum mean delta
    strata = defaultdict(lambda: [0.0, 0])   # sum_delta, n
    for q in qids:
        s = inc[q].get("stratum", "?")
        strata[s][0] += cand[q]["score"] - inc[q]["score"]
        strata[s][1] += 1
    regressing = [
        {"stratum": s, "mean_delta": round(sd / n, 4)}
        for s, (sd, n) in sorted(strata.items())
        if n and (sd / n) < -max_stratum_regression
    ]

    improved = boot.ci_low > 0                 # CI excludes zero, positive side
    no_regression = not regressing
    accepted = improved and no_regression
    if accepted:
        reason = "CI excludes zero (positive) and no stratum regressed"
    elif not improved:
        reason = f"CI does not exclude zero (delta {boot.mean_delta:+.4f}, " \
                 f"CI [{boot.ci_low:+.4f}, {boot.ci_high:+.4f}])"
    else:
        reason = f"stratum regression: {regressing}"

    return GateDecision(
        accepted, round(boot.mean_delta, 4), round(boot.ci_low, 4),
        round(boot.ci_high, 4), len(qids), dropped, regressing, reason)


def private_gate(incumbent: dict, candidate: dict, **kwargs) -> bool:
    """S4: same test, but callers get only the accept/reject bit."""
    return public_gate(incumbent, candidate, **kwargs).accepted
