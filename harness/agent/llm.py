"""Optional LLM NL->SQL leg (Anthropic API). Requires ANTHROPIC_API_KEY.

Enabled by setting the manifest's `agent.nl2sql` to e.g. `anthropic:claude-sonnet-5`.
Read-only by construction: single SELECT statement, validated before execution.
sqlglot-grade AST validation and EXPLAIN cost gates arrive with the production
build; the E0 guard is a strict allowlist check.
"""

from __future__ import annotations

import os
import re

SCHEMA_DDL = """
plans(plan_id, name, tier, monthly_price_cents, unit_cost_cents)
accounts(account_id, name, region, segment, signup_month)  -- region: NA|EU|APAC; segment: smb|mid|enterprise
subscriptions(sub_id, account_id, plan_id, start_month, end_month)  -- 'YYYY-MM' strings; end_month NULL = active
invoices(invoice_id, account_id, plan_id, month, amount_cents, cost_cents, issued_date, paid_date)
support_tickets(ticket_id, account_id, opened_date, resolved_date, severity)  -- resolved_date NULL = unresolved
""".strip()

PROMPT = """You translate a business question into ONE DuckDB SELECT statement.

Schema:
{schema}

Rules:
- Money columns are in CENTS; report USD by dividing by 100.0.
- Months are 'YYYY-MM' strings; compare lexicographically.
- NULL end_month means an active subscription; NULL resolved_date means an unresolved ticket. Never use NOT IN against a column that can be NULL.
- Return ONLY the SQL, no commentary, no code fences.

Question: {question}
"""

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|call|install|load)\b", re.I)


def validate_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("multiple statements are not allowed")
    if not re.match(r"^\s*(with|select)\b", s, re.I):
        raise ValueError("only SELECT statements are allowed")
    if _FORBIDDEN.search(s):
        raise ValueError("statement contains a forbidden keyword")
    return s


class NL2SQL:
    def __init__(self, model: str, db_con):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("agent.nl2sql is enabled but ANTHROPIC_API_KEY is not set")
        import anthropic  # optional extra: pip install .[llm]

        self._client = anthropic.Anthropic()
        self._model = model
        self._con = db_con

    def answer(self, question_text: str, qid: str = ""):
        from .baseline import AgentAnswer

        msg = self._client.messages.create(
            model=self._model,
            max_tokens=800,
            messages=[{"role": "user",
                       "content": PROMPT.format(schema=SCHEMA_DDL, question=question_text)}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text")
        try:
            sql = validate_sql(raw)
            rows = self._con.execute(sql).fetchall()
        except Exception as exc:
            return AgentAnswer("no_answer", None, "nl2sql", f"{type(exc).__name__}: {exc}"[:300])
        if len(rows) == 1 and len(rows[0]) == 1:
            v = rows[0][0]
            return AgentAnswer("scalar", float(v) if v is not None else 0.0, "nl2sql")
        return AgentAnswer("table", [list(r) for r in rows], "nl2sql")
