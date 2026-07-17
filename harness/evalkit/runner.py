"""Eval runner: run an agent over a golden slice, score, aggregate, ledger-log."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from ..synth.questions import Question, load_slice
from .scoring import score


def run_eval(agent, questions: list[Question], manifest_version: str,
             slice_name: str, ledger=None, report_path: str | Path | None = None) -> dict:
    per_question = []
    by_stratum = defaultdict(lambda: [0, 0])
    by_family = defaultdict(lambda: [0, 0])
    route_counts = defaultdict(int)
    tripwire = [0, 0]

    for q in questions:
        ans = agent.answer(q.text, qid=q.qid)
        ok = score(q, ans)
        per_question.append({"qid": q.qid, "correct": ok, "route": ans.route,
                             "stratum": q.stratum, "family": q.family,
                             "tripwire": q.tripwire})
        by_stratum[q.stratum][ok] += 1
        by_family[q.family][ok] += 1
        route_counts[ans.route.split(":")[0]] += 1
        if q.tripwire:
            tripwire[ok] += 1

    def pct(bucket):
        wrong, right = bucket
        total = wrong + right
        return {"n": total, "correct": right,
                "accuracy": round(right / total, 4) if total else None}

    n = len(per_question)
    correct = sum(1 for r in per_question if r["correct"])
    report = {
        "manifest_version": manifest_version,
        "slice": slice_name,
        "n_questions": n,
        "accuracy": round(correct / n, 4) if n else None,
        "by_stratum": {k: pct(v) for k, v in sorted(by_stratum.items())},
        "by_family": {k: pct(v) for k, v in sorted(by_family.items())},
        "tripwires": pct(tripwire),
        "routes": dict(route_counts),
        "per_question": per_question,
    }

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    if ledger is not None:
        summary = {k: v for k, v in report.items() if k != "per_question"}
        ledger.append("eval_run", summary, actor="evalkit")

    return report


def run_slice_file(agent, slice_path: str | Path, manifest_version: str,
                   ledger=None, report_path: str | Path | None = None) -> dict:
    questions = load_slice(slice_path)
    return run_eval(agent, questions, manifest_version,
                    Path(slice_path).stem, ledger, report_path)
