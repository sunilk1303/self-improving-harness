"""Offline tests for the LLM leg: spec dispatch, env guards, SQL validation.

No network: constructors must fail fast and clearly when credentials are
missing, and validation must reject anything that is not one read-only SELECT.
"""

import pytest

from harness.agent.llm import NL2SQL, validate_sql


@pytest.fixture(autouse=True)
def _no_llm_env(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)


def test_bad_specs_rejected():
    with pytest.raises(ValueError, match="provider"):
        NL2SQL("openrouter:some-model", db_con=None)
    with pytest.raises(ValueError, match="spec"):
        NL2SQL("just-a-model-name", db_con=None)


def test_missing_env_fails_fast():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        NL2SQL("anthropic:claude-sonnet-5", db_con=None)
    with pytest.raises(RuntimeError, match="AZURE_OPENAI"):
        NL2SQL("azure-openai:gpt-4o", db_con=None)


def test_validate_sql_accepts_select_and_strips_fences():
    assert validate_sql("SELECT 1") == "SELECT 1"
    assert validate_sql("  select a from t;  ") == "select a from t"
    assert validate_sql("```sql\nSELECT a FROM t\n```") == "SELECT a FROM t"
    assert validate_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


def test_validate_sql_rejects_writes_and_multi_statements():
    for bad in [
        "DROP TABLE accounts",
        "INSERT INTO t VALUES (1)",
        "SELECT 1; SELECT 2",
        "UPDATE t SET a = 1",
        "EXPLAIN SELECT 1",
    ]:
        with pytest.raises(ValueError):
            validate_sql(bad)
