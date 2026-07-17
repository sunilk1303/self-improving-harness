"""Gate statistics: paired bootstrap CIs over questions (stdlib only).

The offline gate contract from docs/04: a candidate beats the incumbent only
if the 95% paired-bootstrap CI of the per-question score delta excludes zero.
A/A calibration runs the same manifest against itself and checks the gate does
NOT fire — the measured false-accept rate and CI width are E0 deliverables.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class BootstrapResult:
    mean_delta: float
    ci_low: float
    ci_high: float
    n_questions: int
    resamples: int

    @property
    def excludes_zero(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def paired_bootstrap(scores_a: list[float], scores_b: list[float],
                     resamples: int = 1000, seed: int = 7,
                     alpha: float = 0.05) -> BootstrapResult:
    """CI for mean(B - A) over paired per-question scores."""
    if len(scores_a) != len(scores_b) or not scores_a:
        raise ValueError("score lists must be equal-length and non-empty")
    n = len(scores_a)
    deltas = [b - a for a, b in zip(scores_a, scores_b)]
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int((alpha / 2) * resamples)]
    hi = means[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return BootstrapResult(sum(deltas) / n, lo, hi, n, resamples)


def aa_calibration(run_scores: list[list[float]], resamples: int = 1000,
                   seed: int = 7) -> dict:
    """All-pairs A/A check across repeated runs of the SAME manifest.

    Returns the false-accept rate (gates that wrongly excluded zero) and the
    mean CI width — the noise floor every later verdict is read against.
    """
    n_runs = len(run_scores)
    if n_runs < 2:
        raise ValueError("need at least 2 runs for A/A calibration")
    fires, widths = 0, []
    pairs = 0
    for i in range(n_runs):
        for j in range(i + 1, n_runs):
            r = paired_bootstrap(run_scores[i], run_scores[j],
                                 resamples=resamples, seed=seed + pairs)
            pairs += 1
            widths.append(r.ci_high - r.ci_low)
            if r.excludes_zero:
                fires += 1
    return {
        "pairs": pairs,
        "false_accept_rate": fires / pairs,
        "mean_ci_width": sum(widths) / len(widths),
        "resamples": resamples,
    }
