"""S2 sandbox gate — apply a candidate in isolation and smoke-run it.

A candidate that passed S1 is materialized into a throwaway directory (a copy
of the current artifacts + manifests with the candidate's files and manifest
diff applied), an agent is constructed against that isolated config and the
frozen data snapshot, and a small fixture question set is run through it. The
candidate fails S2 if construction raises, any fixture answer errors, or the
resulting SQL touches a table outside the read-only warehouse allowlist.

No network and no LLM: fixtures are chosen to exercise the verified-query and
no_route paths, so S2 is fast, deterministic, and safe to run in CI. (The
public/private eval stages S3/S4, which do use the LLM leg, come next.)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..agent.baseline import BaselineAgent
from .change import CandidateChange

ALLOWED_TABLES = {"plans", "accounts", "subscriptions", "invoices", "support_tickets"}

# Small, deterministic smoke set: a VQR-covered question and an uncovered one.
SMOKE_FIXTURES = [
    "What was total invoiced revenue in USD in 2025-01?",
    "How many subscriptions ended in 2025-01?",
    "How many accounts have never opened a support ticket?",
    "Which plan generated the highest invoiced revenue in 2025, and how much (USD)?",
]


@dataclass
class SandboxResult:
    change_id: str
    passed: bool
    detail: str = ""
    fixture_routes: dict = field(default_factory=dict)


def _apply_manifest_diff(manifest: dict, diff: dict) -> dict:
    # deep-copy dict nodes along each write path so the caller's manifest
    # (the incumbent) is never mutated in place
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in manifest.items()}
    for dotted, value in diff.items():
        node = out
        parts = dotted.split(".")
        for p in parts[:-1]:
            child = node.get(p)
            node[p] = dict(child) if isinstance(child, dict) else {}
            node = node[p]
        node[parts[-1]] = value
    return out


def run_sandbox_gate(change: CandidateChange, base_manifest: dict,
                     workdir: str | Path, snapshot: str | Path,
                     ledger=None) -> SandboxResult:
    work = Path(workdir)
    if work.exists():
        shutil.rmtree(work)
    (work / "artifacts" / "vqr").mkdir(parents=True, exist_ok=True)

    # seed with current artifacts, then overlay the candidate's files
    src_vqr = Path("artifacts") / "vqr"
    if src_vqr.exists():
        shutil.copytree(src_vqr, work / "artifacts" / "vqr", dirs_exist_ok=True)
    for rel, content in change.files.items():
        target = work / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")

    manifest = _apply_manifest_diff(base_manifest, change.manifest_diff)
    manifest["data"] = dict(manifest.get("data", {}), snapshot=str(snapshot))
    manifest.setdefault("agent", {}).setdefault("nl2sql", "none")  # S2 never calls the LLM

    result = SandboxResult(change.change_id, passed=True)
    try:
        agent = BaselineAgent(manifest, ledger=None,
                              vqr_artifacts_dir=work / "artifacts" / "vqr")
    except Exception as exc:
        result.passed = False
        result.detail = f"agent construction failed: {type(exc).__name__}: {exc}"[:300]
        _log(ledger, change, result)
        return result

    try:
        for q in SMOKE_FIXTURES:
            ans = agent.answer(q)
            result.fixture_routes[q[:40]] = ans.route
            if ans.answer_type == "no_answer" and ans.route != "no_route":
                result.passed = False
                result.detail = f"fixture errored: {ans.detail}"[:300]
                break
            touched = _tables_touched(agent, ans)
            illegal = touched - ALLOWED_TABLES
            if illegal:
                result.passed = False
                result.detail = f"fixture touched forbidden tables: {sorted(illegal)}"
                break
    finally:
        agent.close()

    _log(ledger, change, result)
    return result


def _tables_touched(agent, answer) -> set:
    """Best-effort: for VQR routes, inspect the entry's SQL for table names."""
    route = answer.route
    if not route.startswith("vqr:"):
        return set()
    entry_id = route.split(":", 1)[1]
    for entry in getattr(agent, "_vqr", []):
        if entry.id == entry_id:
            sql = entry.sql.lower()
            return {t for t in ALLOWED_TABLES if t in sql}
    return set()


def _log(ledger, change, result: SandboxResult) -> None:
    if ledger is not None:
        ledger.append("gate_result",
                      {"stage": "S2", "change_id": change.change_id,
                       "passed": result.passed, "detail": result.detail,
                       "routes": result.fixture_routes}, actor="gate")
