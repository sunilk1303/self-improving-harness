from harness.synth.questions import _split_for, emit


def test_emission_shape(questions):
    assert len(questions) >= 100
    strata = {q.stratum for q in questions}
    assert strata == {"single_table", "multi_join", "federated", "narrative"}
    families = {q.family for q in questions}
    assert families == {"revenue", "churn", "margin"}
    assert sum(1 for q in questions if q.tripwire) >= 5


def test_split_is_deterministic_and_disjoint(questions):
    for q in questions:
        assert q.slice == _split_for(q.qid)
    slices = {q.slice for q in questions}
    assert slices == {"public", "private"}
    # roughly the configured fraction, generously bounded
    private = sum(1 for q in questions if q.slice == "private")
    assert 0.10 < private / len(questions) < 0.45


def test_expected_types(questions):
    for q in questions:
        if q.answer_type == "scalar":
            assert isinstance(q.expected, (int, float))
        elif q.answer_type == "table":
            assert isinstance(q.expected, list) and q.expected
        elif q.answer_type == "facts":
            assert isinstance(q.expected, dict) and q.expected
        else:
            raise AssertionError(f"unknown answer_type {q.answer_type}")


def test_tripwire_discontinued_plan_is_zero(questions):
    t1 = [q for q in questions if q.qid.startswith("T1-")]
    assert t1
    assert all(q.expected == 0.0 for q in t1)


def test_reseed_rotates_answers(tmp_path, db_path, params, questions):
    """Private-slice rotation = reseed: same qids, different planted answers."""
    from harness.synth.generator import PlantedParams, generate

    p2 = PlantedParams(seed=params.seed + 1, n_accounts=params.n_accounts,
                       n_months=params.n_months)
    db2 = tmp_path / "reseed.duckdb"
    generate(db2, p2)
    q2 = {q.qid: q for q in emit(db2, p2)}
    scalars = [q for q in questions if q.answer_type == "scalar" and q.expected][:20]
    assert scalars
    changed = sum(1 for q in scalars if q2[q.qid].expected != q.expected)
    assert changed >= len(scalars) * 0.8
