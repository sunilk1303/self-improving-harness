"""Cascade orchestration tests — mock eval_fn, deterministic sandbox, no network."""

import pytest

from harness.gate.change import CandidateChange
from harness.gate.cascade import run_cascade

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
"""


@pytest.fixture
def base_manifest(db_path):
    return {"version": "v0", "agent": {"router": "vqr-first", "nl2sql": "none",
            "vqr_version": "v0"}, "data": {"snapshot": str(db_path)}}


def _report(scores):
    return {"per_question": [{"qid": q, "score": s, "stratum": "single_table"}
                             for q, s in scores.items()]}


def _good_change():
    return CandidateChange("cand-good", "add VQs", "T2",
                           files={"artifacts/vqr/v1.yaml": GOOD_VQR_V1},
                           manifest_diff={"agent.vqr_version": "v1"})


def test_fabrication_stops_at_s1(base_manifest, db_path, tmp_path):
    change = _good_change()
    change.declared_tier = "T0"  # real tier is T2 -> fabrication
    r = run_cascade(change, base_manifest, snapshot=db_path,
                    workdir=tmp_path / "s", eval_fn=lambda m, s: _report({}))
    assert not r.accepted and r.failed_at == "S1" and r.fabrication


def test_full_pass_when_eval_improves(base_manifest, db_path, tmp_path):
    inc = _report({f"q{i}": 0.0 for i in range(80)})
    cand = _report({f"q{i}": (1.0 if i < 40 else 0.0) for i in range(80)})

    def eval_fn(manifest, slice_name):
        return cand if manifest["agent"].get("vqr_version") == "v1" else inc

    r = run_cascade(_good_change(), base_manifest, snapshot=db_path,
                    workdir=tmp_path / "s", eval_fn=eval_fn)
    assert r.accepted and r.reached == "S4"
    assert r.public.accepted and r.private_accept


def test_rejected_at_s3_when_no_improvement(base_manifest, db_path, tmp_path):
    flat = _report({f"q{i}": (1.0 if i % 2 else 0.0) for i in range(80)})
    r = run_cascade(_good_change(), base_manifest, snapshot=db_path,
                    workdir=tmp_path / "s", eval_fn=lambda m, s: flat)
    assert not r.accepted and r.failed_at == "S3"


def test_broken_sql_stops_at_s2(base_manifest, db_path, tmp_path):
    broken = GOOD_VQR_V1.replace("FROM invoices WHERE month = ?",
                                 "FROM nonexistent WHERE month = ?")
    change = CandidateChange("cand-broken", "typo", "T2",
                             files={"artifacts/vqr/v1.yaml": broken},
                             manifest_diff={"agent.vqr_version": "v1"})
    r = run_cascade(change, base_manifest, snapshot=db_path,
                    workdir=tmp_path / "s", eval_fn=lambda m, s: _report({}))
    assert not r.accepted and r.failed_at == "S2"
