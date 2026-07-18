import pytest

from harness.agent.vqr import load_vqr


def test_v0_artifact_loads_and_binds():
    entries = load_vqr("v0")
    assert len(entries) == 6
    by_id = {e.id: e for e in entries}

    e = by_id["vq-segment-region-revenue"]
    m = e.match("What was total invoiced revenue in USD from smb accounts in NA in 2024-05?")
    assert m
    assert e.bind(m) == ["2024-05", "smb", "NA"]

    e = by_id["vq-plan-revenue-month"]
    m = e.match("What was invoiced revenue in USD from the 'Starter Legacy' plan in 2024-11?")
    assert m
    assert e.bind(m) == ["Starter Legacy", "2024-11"]

    # total-revenue pattern must NOT swallow the segment/region variant
    e = by_id["vq-total-revenue"]
    assert not e.match("What was total invoiced revenue in USD from smb accounts in NA in 2024-05?")
    assert e.match("What was total invoiced revenue in USD in 2024-05?")


def _write_artifact(tmp_path, version, entries_yaml):
    d = tmp_path / "vqr"
    d.mkdir()
    (d / f"{version}.yaml").write_text(
        f"version: {version}\nentries:\n{entries_yaml}", encoding="utf-8")
    return d


def test_loader_rejects_write_sql(tmp_path):
    d = _write_artifact(tmp_path, "vx", """
  - id: bad
    question_pattern: 'drop it\\?$'
    sql: DROP TABLE accounts
    params: []
""")
    with pytest.raises(ValueError):
        load_vqr("vx", artifacts_dir=d)


def test_loader_rejects_param_mismatch(tmp_path):
    d = _write_artifact(tmp_path, "vy", """
  - id: bad-params
    question_pattern: 'revenue in (?P<month>\\d{4}-\\d{2})\\?$'
    sql: SELECT 1 FROM invoices WHERE month = ? AND region = ?
    params: [month]
""")
    with pytest.raises(ValueError, match="placeholder"):
        load_vqr("vy", artifacts_dir=d)


def test_loader_rejects_duplicate_ids(tmp_path):
    d = _write_artifact(tmp_path, "vz", """
  - id: dup
    question_pattern: 'a\\?$'
    sql: SELECT 1
    params: []
  - id: dup
    question_pattern: 'b\\?$'
    sql: SELECT 2
    params: []
""")
    with pytest.raises(ValueError, match="duplicate"):
        load_vqr("vz", artifacts_dir=d)
