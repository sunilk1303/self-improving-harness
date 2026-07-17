"""Generate the small document corpus with planted (and deliberately stale) facts.

The docs are the knowledge-base leg's substrate. One pricing doc is
deliberately STALE relative to the invoices table (it predates the EU price
change) — the planted freshness/conflict trap for federated questions.
"""

from __future__ import annotations

from pathlib import Path

from .generator import PLANS, PlantedParams


def generate_docs(docs_dir: str | Path, params: PlantedParams) -> list[Path]:
    d = Path(docs_dir)
    d.mkdir(parents=True, exist_ok=True)
    written = []

    pricing_rows = "\n".join(
        f"| {name} | {tier} | ${price / 100:,.2f} |" for name, tier, price, _ in PLANS
    )
    docs = {
        # STALE ON PURPOSE: written before the EU price change, never updated.
        "pricing-policy.md": f"""# Pricing Policy (v1, effective 2024-01)

Monthly list prices by plan:

| Plan | Tier | Monthly price |
|------|------|--------------|
{pricing_rows}

Prices apply uniformly across all regions.
""",
        "metric-definitions.md": f"""# Metric Definitions

- **Churn**: an account is churned in month M if its subscription has
  end_month = M. Churn rate for a cohort = churned accounts / accounts active
  at the start of M.
- **Gross margin**: (invoiced amount - unit cost) / invoiced amount, computed
  from the invoices table. Amounts are stored in CENTS.
- **Active account**: an account with a subscription whose end_month is NULL
  or in the future.
""",
        "product-notes.md": f"""# Product Notes

- The **{params.discontinued_plan}** plan was discontinued after
  {params.discontinued_after}; remaining customers were migrated to Starter.
- EU pricing was adjusted in {params.eu_price_change_month} (+{params.eu_price_increase:.0%}
  list price) to cover rising regional delivery costs.
- Support has been investing in faster resolution times through 2025.
""",
    }
    for name, text in docs.items():
        path = d / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
