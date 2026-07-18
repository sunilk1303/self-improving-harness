"""Eval runner: run an agent over a golden slice, score, aggregate, ledger-log.

Multi-generation scoring: each question may be answered `generations` times and
its score is the mean of the per-generation binary scores — this is what
absorbs LLM nondeterminism into the paired-bootstrap gate (docs/04). Routes
that are deterministic by construction (verified queries, no_route) stop after
one generation, so extra generations cost only LLM-routed questions.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from ..synth.questions import Question, load_slice
from .scoring import score

_DETERMINISTIC_ROUTES = ("vqr", "no_route")


def run_eval(agent, questions: list[Question], manifest_version: str,
             slice_name: str, ledger=None, report_path: str | Path | None = None,
             generations: int = 1) -> dict:
    per_question = []
    by_stratum = defaultdict(lambda: [0, 0.0])   # [n, score_sum]
    by_family = defaultdict(lambda: [0, 0.0])
    route_counts = defaultdict(int)
    tripwire = [0, 0.0]

    for q in questions:
        gen_scores = []
        route = "?"
        for _ in range(max(1, generations)):
            ans = agent.answer(q.text, qid=q.qid)
            gen_scores.append(1.0 if score(q, ans) else 0.0)
            route = ans.route
            if route.split(":")[0] in _DETERMINISTIC_ROUTES:
                break
        qscore = sum(gen_scores) / len(gen_scores)

        per_question.append({"qid": q.qid, "score": qscore,
                             "generations": len(gen_scores), "route": route,
                             "stratum": q.stratum, "family": q.family,
                             "tripwire": q.tripwire})
        by_stratum[q.stratum][0] += 1
        by_stratum[q.stratum][1] += qscore
        by_family[q.family][0] += 1
        by_family[q.family][1] += qscore
        route_counts[route.split(":")[0]] += 1
        if q.tripwire:
            tripwire[0] += 1
            tripwire[1] += qscore

    def pct(bucket):
        n, s = bucket
        return {"n": n, "mean_score": round(s / n, 4) if n else None}

    n = len(per_question)
    total = sum(r["score"] for r in per_question)
    report = {
        "manifest_version": manifest_version,
        "slice": slice_name,
        "n_questions": n,
        "generations": generations,
        "accuracy": round(total / n, 4) if n else None,
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
                   ledger=None, report_path: str | Path | None = None,
                   generations: int = 1) -> dict:
    questions = load_slice(slice_path)
    return run_eval(agent, questions, manifest_version,
                    Path(slice_path).stem, ledger, report_path,
                    generations=generations)
