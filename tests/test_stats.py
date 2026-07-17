import random

from harness.evalkit.stats import aa_calibration, paired_bootstrap


def test_identical_runs_never_fire():
    scores = [random.Random(1).random() for _ in range(120)]
    r = paired_bootstrap(scores, scores)
    assert r.mean_delta == 0.0
    assert not r.excludes_zero


def test_real_shift_fires():
    rng = random.Random(2)
    a = [1.0 if rng.random() < 0.5 else 0.0 for _ in range(300)]
    b = [1.0 if x == 1.0 or rng.random() < 0.25 else 0.0 for x in a]  # clear lift
    r = paired_bootstrap(a, b)
    assert r.mean_delta > 0
    assert r.excludes_zero


def test_noise_does_not_fire():
    rng = random.Random(3)
    base = [1.0 if rng.random() < 0.6 else 0.0 for _ in range(200)]
    flip = list(base)
    i = rng.randrange(len(flip))
    flip[i] = 1.0 - flip[i]  # one-question difference is noise
    r = paired_bootstrap(base, flip)
    assert not r.excludes_zero


def test_aa_calibration_on_identical_runs():
    scores = [1.0, 0.0] * 60
    result = aa_calibration([scores, list(scores), list(scores)])
    assert result["pairs"] == 3
    assert result["false_accept_rate"] == 0.0
    assert result["mean_ci_width"] == 0.0
