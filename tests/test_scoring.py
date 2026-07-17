from harness.evalkit.scoring import score_facts, score_scalar, score_table


def test_scalar():
    assert score_scalar(100.0, 100.0)
    assert score_scalar(100.0, 100.00000001)
    assert not score_scalar(100.0, 101.0)
    assert not score_scalar(100.0, None)
    assert score_scalar(0.0, 0.0)


def test_table_order_and_type_normalization():
    expected = [["Enterprise", 1234.5], ["Growth", 99.0]]
    assert score_table(expected, [["growth", 99.0], ["ENTERPRISE", 1234.5]])
    assert not score_table(expected, [["Growth", 99.0]])          # row count
    assert not score_table(expected, [["Growth", 99.0], ["Enterprise", 1000.0]])


def test_facts_from_text_and_dict():
    expected = {"direction": "worsened", "q1_days": 6.1, "q2_days": 10.9}
    text = ("Resolution time worsened: Q1 averaged 6.1 days while Q2 averaged "
            "10.9 days.")
    assert score_facts(expected, text)
    assert not score_facts(expected, "It improved from 6.1 to 5.0 days.")
    assert score_facts(expected, {"direction": "Worsened", "q1_days": 6.1,
                                  "q2_days": 10.9})
    assert not score_facts(expected, {"direction": "worsened", "q1_days": 6.1})


def test_facts_numeric_tolerance():
    assert score_facts({"pct": 12.30}, "revenue rose about 12.4 percent")
    assert not score_facts({"pct": 12.30}, "revenue rose about 15 percent")
