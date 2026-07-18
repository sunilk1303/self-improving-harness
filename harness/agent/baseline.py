"""Baseline insight agent: verified-query-first router with typed fallback.

Route order (mirrors docs/02's "semantic layer first"):
  1. Verified Query Repository — parameterized, human-trusted SQL matched by
     pattern. Serving via VQR is the governed path.
  2. LLM NL->SQL fallback (optional; needs an API key and a manifest opt-in).
     Every fallback is a logged `metric_fallback` limitation signal — the
     highest-yield improvement signal in the design.
  3. No route -> typed `no_route` limitation event. The agent never guesses.

The E0 VQR deliberately covers only part of the question space (single-table
metrics and one join family). The uncovered remainder is the honest headroom
the self-improvement loop must earn in E3 — do not "fix" this by widening the
VQR to match the golden set, which would be eval contamination by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from .vqr import ARTIFACTS_DIR, load_vqr


@dataclass
class AgentAnswer:
    answer_type: str          # scalar | table | text | no_answer
    value: object
    route: str                # vqr:<id> | nl2sql | no_route
    detail: str = ""


class BaselineAgent:
    def __init__(self, manifest: dict, ledger=None, vqr_artifacts_dir=None):
        self.manifest = manifest
        self.ledger = ledger
        self.db_path = manifest["data"]["snapshot"]
        self._con = duckdb.connect(str(Path(self.db_path)), read_only=True)
        # VQR is a manifest-pinned artifact, not code: load the pinned version.
        vqr_version = manifest["agent"].get("vqr_version", "v0")
        self._vqr = load_vqr(vqr_version, vqr_artifacts_dir or ARTIFACTS_DIR)
        nl2sql = manifest["agent"].get("nl2sql", "none")
        self._llm = None
        if nl2sql and nl2sql != "none":
            from .llm import NL2SQL  # optional dependency, imported lazily
            self._llm = NL2SQL(nl2sql, db_con=self._con)

    def _log(self, event_type: str, payload: dict) -> None:
        if self.ledger is not None:
            payload = {**payload, "manifest_version": self.manifest.get("version")}
            self.ledger.append(event_type, payload, actor="baseline-agent")

    def answer(self, question_text: str, qid: str = "") -> AgentAnswer:
        # 1) verified queries — the governed path
        for entry in self._vqr:
            m = entry.match(question_text)
            if m:
                try:
                    rows = self._con.execute(entry.sql, entry.bind(m)).fetchall()
                except Exception as exc:  # execution failure is a typed limitation
                    self._log("limitation_registered",
                              {"type": "sql_error", "qid": qid,
                               "route": f"vqr:{entry.id}", "error": str(exc)[:500]})
                    return AgentAnswer("no_answer", None, f"vqr:{entry.id}",
                                       str(exc)[:200])
                if len(rows) == 1 and len(rows[0]) == 1:
                    v = rows[0][0]
                    return AgentAnswer("scalar", float(v) if v is not None else 0.0,
                                       f"vqr:{entry.id}")
                return AgentAnswer("table", [list(r) for r in rows], f"vqr:{entry.id}")

        # 2) LLM NL->SQL fallback — every use is a coverage-gap signal
        if self._llm is not None:
            self._log("limitation_registered",
                      {"type": "metric_fallback", "qid": qid,
                       "question": question_text[:300]})
            return self._llm.answer(question_text, qid)

        # 3) no route: the agent does not guess
        self._log("limitation_registered",
                  {"type": "no_route", "qid": qid, "question": question_text[:300]})
        return AgentAnswer("no_answer", None, "no_route",
                           "no verified query matched and no NL2SQL leg configured")

    def close(self) -> None:
        self._con.close()
