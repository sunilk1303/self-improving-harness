"""End-to-end: baseline agent over emitted goldens, scored by the eval kit."""

from harness.agent.baseline import BaselineAgent
from harness.ledger import Ledger
from harness.evalkit.runner import run_eval


def _make_agent(db_path, ledger=None) -> BaselineAgent:
    manifest = {
        "version": "v0-test",
        "agent": {"router": "vqr-first", "nl2sql": "none", "vqr_version": "v0"},
        "data": {"snapshot": str(db_path), "docs_dir": ""},
    }
    return BaselineAgent(manifest, ledger=ledger)


def test_vqr_answers_are_correct_and_gaps_are_typed(db_path, questions, tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    agent = _make_agent(db_path, ledger)
    report = run_eval(agent, questions, "v0-test", "all", ledger=ledger)
    agent.close()

    per_q = report["per_question"]
    vqr = [r for r in per_q if r["route"].startswith("vqr:")]
    no_route = [r for r in per_q if r["route"] == "no_route"]

    # the governed path must be exactly right wherever it routes
    assert vqr, "VQR matched nothing — router patterns are broken"
    assert all(r["score"] == 1.0 for r in vqr)

    # honest headroom: part of the space is deliberately unrouted at E0
    assert no_route, "expected uncovered questions at E0"
    assert all(r["score"] == 0.0 for r in no_route)

    # overall accuracy = VQR coverage; sane band, not suspiciously high
    assert 0.30 < report["accuracy"] < 0.90

    # every gap became a typed limitation event on a verified chain
    ok, msg = ledger.verify()
    assert ok, msg
    text = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert '"no_route"' in text
    assert '"eval_run"' in text


def test_agent_never_guesses(db_path, questions):
    agent = _make_agent(db_path)
    unrouted = next(q for q in questions if q.stratum == "narrative")
    ans = agent.answer(unrouted.text, qid=unrouted.qid)
    agent.close()
    assert ans.answer_type == "no_answer"
    assert ans.route == "no_route"
