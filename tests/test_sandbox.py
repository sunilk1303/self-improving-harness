"""S2 sandbox gate tests — deterministic (v0 path), no network."""

import pytest

from harness.agent.baseline import BaselineAgent
from harness.gate.change import CandidateChange
from harness.gate.sandbox import run_sandbox_gate

GOOD_VQR_V1 = """version: v1
entries:
  - id: vq-total-revenue
    question_pattern: 'total invoiced revenue in USD in (?P<month>\\d{4}-\\d{2})\\?$'
    sql: SELECT SUM(amount_cents)/100.0 FROM invoices WHERE month = ?
    params: [month]
  - id: vq-subs-ended
    question_pattern: 'how many subscriptions ended in (?P<month>\\d{4}-\\d{2})\\?$'
    sql: SELECT COUNT(*) FROM subscriptions WHERE end_month = ?
    params: [month]
  - id: vq-accounts-no-tickets
    question_pattern: 'how many accounts have never opened a support ticket\\?$'
    sql: >-
      SELECT COUNT(*) FROM accounts a WHERE NOT EXISTS
      (SELECT 1 FROM support_tickets t WHERE t.account_id = a.account_id)
    params: []
  - id: vq-plan-top-revenue
    question_pattern: 'highest invoiced revenue in (?P<year>\\d{4}), and how much'
    sql: >-
      SELECT p.name, SUM(i.amount_cents)/100.0 AS rev FROM invoices i
      JOIN plans p USING (plan_id) WHERE i.month LIKE ? GROUP BY 1
      ORDER BY rev DESC LIMIT 1
    params: [year]
"""


@pytest.fixture
def base_manifest(db_path):
    return {"version": "v0", "agent": {"router": "vqr-first", "nl2sql": "none",
            "vqr_version": "v0"}, "data": {"snapshot": str(db_path)}}


def test_good_vqr_change_passes_sandbox(base_manifest, db_path, tmp_path):
    # a real v1 artifact must exist under the sandbox's seed dir for vqr_version=v1
    change = CandidateChange(
        "cand-good", "add verified queries", "T2",
        files={"artifacts/vqr/v1.yaml": GOOD_VQR_V1},
        manifest_diff={"agent.vqr_version": "v1"})
    result = run_sandbox_gate(change, base_manifest,
                              workdir=tmp_path / "sbx", snapshot=db_path)
    assert result.passed, result.detail
    # the new plan-top-revenue query should now route via VQR, not no_route
    routes = set(result.fixture_routes.values())
    assert any(r.startswith("vqr:") for r in routes)


def test_broken_sql_change_fails_sandbox(base_manifest, db_path, tmp_path):
    broken = GOOD_VQR_V1.replace(
        "SELECT SUM(amount_cents)/100.0 FROM invoices WHERE month = ?",
        "SELECT SUM(amount_cents)/100.0 FROM nonexistent_table WHERE month = ?")
    change = CandidateChange(
        "cand-broken", "typo table name", "T2",
        files={"artifacts/vqr/v1.yaml": broken},
        manifest_diff={"agent.vqr_version": "v1"})
    result = run_sandbox_gate(change, base_manifest,
                              workdir=tmp_path / "sbx", snapshot=db_path)
    assert not result.passed
    assert "errored" in result.detail or "construction failed" in result.detail
