"""S3/S4 eval-gate decision tests — pure, no agents, no network."""

from harness.gate.eval_gate import public_gate, private_gate


def _report(scores_by_qid, strata=None):
    strata = strata or {}
    return {"per_question": [
        {"qid": q, "score": s, "stratum": strata.get(q, "single_table")}
        for q, s in scores_by_qid.items()]}


def test_clear_improvement_accepted():
    inc = _report({f"q{i}": (1.0 if i < 30 else 0.0) for i in range(100)})
    # candidate fixes 20 of the previously-wrong questions, breaks none
    cand = _report({f"q{i}": (1.0 if i < 50 else 0.0) for i in range(100)})
    d = public_gate(inc, cand)
    assert d.accepted
    assert d.ci_low > 0
    assert d.n_paired == 100


def test_noop_not_accepted():
    scores = {f"q{i}": (1.0 if i % 2 == 0 else 0.0) for i in range(100)}
    d = public_gate(_report(scores), _report(dict(scores)))
    assert not d.accepted
    assert d.mean_delta == 0.0


def test_pooled_gain_but_hard_stratum_regresses_is_rejected():
    # 90 easy questions improve; 10 hard questions all regress 1->0.
    inc_scores, cand_scores, strata = {}, {}, {}
    for i in range(90):
        inc_scores[f"e{i}"] = 0.0
        cand_scores[f"e{i}"] = 1.0 if i < 40 else 0.0   # +40 easy wins
        strata[f"e{i}"] = "multi_join"
    for i in range(10):
        inc_scores[f"h{i}"] = 1.0
        cand_scores[f"h{i}"] = 0.0                       # hard stratum wiped out
        strata[f"h{i}"] = "federated"
    d = public_gate(_report(inc_scores, strata), _report(cand_scores, strata))
    assert not d.accepted
    assert any(r["stratum"] == "federated" for r in d.regressing_strata)


def test_dropped_questions_counted():
    inc = _report({"a": 1.0, "b": 0.0, "c": 1.0})
    cand = _report({"a": 1.0, "b": 1.0, "d": 1.0})   # c missing, d extra
    d = public_gate(inc, cand)
    assert d.n_paired == 2
    assert d.n_dropped == 2


def test_private_gate_returns_bit():
    inc = _report({f"q{i}": 0.0 for i in range(80)})
    cand = _report({f"q{i}": (1.0 if i < 40 else 0.0) for i in range(80)})
    assert private_gate(inc, cand) is True
    assert private_gate(inc, _report({f"q{i}": 0.0 for i in range(80)})) is False
