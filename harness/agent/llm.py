"""Optional LLM NL->SQL leg, provider-dispatched via the manifest spec.

Manifest `agent.nl2sql` values:
  - "anthropic:<model>"          e.g. anthropic:claude-sonnet-5
                                 needs ANTHROPIC_API_KEY
  - "azure-openai:<deployment>"  e.g. azure-openai:gpt-4o (the *deployment* name)
                                 needs AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT
                                 (AZURE_OPENAI_API_VERSION optional, default 2024-10-21)

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
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def validate_sql(sql: str) -> str:
    s = sql.strip()
    s = _FENCE.sub("", s).strip()  # models wrap in fences despite instructions
    s = s.rstrip(";").strip()
    if ";" in s:
        raise ValueError("multiple statements are not allowed")
    if not re.match(r"^\s*(with|select)\b", s, re.I):
        raise ValueError("only SELECT statements are allowed")
    if _FORBIDDEN.search(s):
        raise ValueError("statement contains a forbidden keyword")
    return s


def _anthropic_completer(model: str):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("agent.nl2sql uses anthropic but ANTHROPIC_API_KEY is not set")
    import anthropic  # optional extra: pip install .[llm]

    client = anthropic.Anthropic()

    def complete(prompt: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    return complete


def _azure_openai_completer(deployment: str):
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not key or not endpoint:
        raise RuntimeError(
            "agent.nl2sql uses azure-openai but AZURE_OPENAI_API_KEY and/or "
            "AZURE_OPENAI_ENDPOINT are not set")
    from openai import AzureOpenAI  # optional extra: pip install .[llm]

    client = AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )

    def complete(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=deployment,  # Azure routes by deployment name
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    return complete


_PROVIDERS = {
    "anthropic": _anthropic_completer,
    "azure-openai": _azure_openai_completer,
}


class NL2SQL:
    def __init__(self, spec: str, db_con):
        provider, _, model = spec.partition(":")
        if not model:
            raise ValueError(f"nl2sql spec must be '<provider>:<model>', got {spec!r}")
        if provider not in _PROVIDERS:
            raise ValueError(f"unknown nl2sql provider {provider!r}; "
                             f"known: {sorted(_PROVIDERS)}")
        self._complete = _PROVIDERS[provider](model)
        self._con = db_con

    def answer(self, question_text: str, qid: str = ""):
        from .baseline import AgentAnswer

        # Any failure — API (auth, billing, rate limit), validation, or
        # execution — is a typed no_answer, never a crashed eval run.
        try:
            raw = self._complete(PROMPT.format(schema=SCHEMA_DDL, question=question_text))
            sql = validate_sql(raw)
            rows = self._con.execute(sql).fetchall()
        except Exception as exc:
            return AgentAnswer("no_answer", None, "nl2sql", f"{type(exc).__name__}: {exc}"[:300])
        if len(rows) == 1 and len(rows[0]) == 1:
            v = rows[0][0]
            return AgentAnswer("scalar", float(v) if v is not None else 0.0, "nl2sql")
        return AgentAnswer("table", [list(r) for r in rows], "nl2sql")
