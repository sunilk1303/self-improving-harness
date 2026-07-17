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

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass
class AgentAnswer:
    answer_type: str          # scalar | table | text | no_answer
    value: object
    route: str                # vqr:<id> | nl2sql | no_route
    detail: str = ""


# --- Verified Query Repository (v0) ----------------------------------------
# Each entry: (vqr_id, compiled question pattern, SQL, param builder)
MONTH = r"(?P<month>\d{4}-\d{2})"

VQR = [
    ("vq-total-revenue",
     re.compile(rf"total invoiced revenue in USD in {MONTH}\?$", re.I),
     "SELECT SUM(amount_cents)/100.0 FROM invoices WHERE month = ?",
     lambda m: [m["month"]]),
    ("vq-subs-ended",
     re.compile(rf"how many subscriptions ended in {MONTH}\?$", re.I),
     "SELECT COUNT(*) FROM subscriptions WHERE end_month = ?",
     lambda m: [m["month"]]),
    ("vq-gross-margin",
     re.compile(rf"gross margin \(percent of invoiced revenue\) in {MONTH}\?$", re.I),
     "SELECT 100.0 * (SUM(amount_cents) - SUM(cost_cents)) / SUM(amount_cents) "
     "FROM invoices WHERE month = ?",
     lambda m: [m["month"]]),
    ("vq-segment-region-revenue",
     re.compile(rf"revenue in USD from (?P<segment>\w+) accounts in (?P<region>\w+) "
                rf"in {MONTH}\?$", re.I),
     "SELECT COALESCE(SUM(i.amount_cents), 0)/100.0 "
     "FROM invoices i JOIN accounts a USING (account_id) "
     "WHERE i.month = ? AND a.segment = ? AND a.region = ?",
     lambda m: [m["month"], m["segment"], m["region"]]),
    ("vq-plan-revenue-month",
     re.compile(rf"revenue in USD from the '(?P<plan>[^']+)' plan in {MONTH}\?$", re.I),
     "SELECT COALESCE(SUM(i.amount_cents), 0)/100.0 FROM invoices i "
     "JOIN plans p USING (plan_id) WHERE p.name = ? AND i.month = ?",
     lambda m: [m["plan"], m["month"]]),
    ("vq-accounts-no-tickets",
     re.compile(r"how many accounts have never opened a support ticket\?$", re.I),
     "SELECT COUNT(*) FROM accounts a WHERE NOT EXISTS "
     "(SELECT 1 FROM support_tickets t WHERE t.account_id = a.account_id)",
     lambda m: []),
]


class BaselineAgent:
    def __init__(self, manifest: dict, ledger=None):
        self.manifest = manifest
        self.ledger = ledger
        self.db_path = manifest["data"]["snapshot"]
        self._con = duckdb.connect(str(Path(self.db_path)), read_only=True)
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
        for vqr_id, pattern, sql, build in VQR:
            m = pattern.search(question_text.strip())
            if m:
                try:
                    rows = self._con.execute(sql, build(m.groupdict())).fetchall()
                except Exception as exc:  # execution failure is a typed limitation
                    self._log("limitation_registered",
                              {"type": "sql_error", "qid": qid, "route": f"vqr:{vqr_id}",
                               "error": str(exc)[:500]})
                    return AgentAnswer("no_answer", None, f"vqr:{vqr_id}", str(exc)[:200])
                if len(rows) == 1 and len(rows[0]) == 1:
                    v = rows[0][0]
                    return AgentAnswer("scalar", float(v) if v is not None else 0.0,
                                       f"vqr:{vqr_id}")
                return AgentAnswer("table", [list(r) for r in rows], f"vqr:{vqr_id}")

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
