"""Seeded synthetic-business generator whose planted parameters ARE the hidden answers.

Generates a small SaaS subscription business (plans, accounts, subscriptions,
invoices, support tickets) into DuckDB. All randomness flows from one seed, so
the same seed reproduces the same warehouse byte-for-byte at the row level —
and private-slice rotation is a reseed.

Planted facts (the ground truth the eval harness scores against):
  * Base monthly churn differs by segment (smb highest).
  * Enterprise accounts with >2 unresolved tickets churn at a large multiple
    of the enterprise base rate.
  * An EU price change (price up, unit cost up more) drops EU gross margin by
    several points from ``eu_price_change_month`` onward.
  * One plan is discontinued mid-history (tripwire: revenue after that month
    is exactly zero, though a plausible-sounding answer would be nonzero).
  * Ticket resolution time worsens sharply in one quarter (sign-flip tripwire).

Enterprise nastiness is deliberate: money is stored in CENTS, unresolved
tickets have NULL resolved_date (NOT IN + NULL traps), and some accounts have
no tickets at all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import duckdb

REGIONS = ["NA", "EU", "APAC"]
SEGMENTS = ["smb", "mid", "enterprise"]


@dataclass(frozen=True)
class PlantedParams:
    """Everything the eval harness may treat as known-by-construction."""

    seed: int = 1303
    n_accounts: int = 1200
    start_month: str = "2024-01"
    n_months: int = 24

    # base monthly churn probability by segment (smb plainly highest)
    base_churn: dict = field(
        default_factory=lambda: {"smb": 0.050, "mid": 0.030, "enterprise": 0.012}
    )
    # enterprise accounts with >2 unresolved tickets churn at this multiple
    ticket_churn_multiplier: float = 3.0

    # EU price change: prices up 10%, unit costs up 25% -> planted margin drop
    eu_price_change_month: str = "2025-03"
    eu_price_increase: float = 0.10
    eu_cost_increase: float = 0.25

    # tripwire: plan discontinued after this month (no invoices afterwards)
    discontinued_plan: str = "Starter Legacy"
    discontinued_after: str = "2024-09"

    # sign-flip tripwire: resolution times worsen in this quarter
    resolution_worsen_quarter: str = "2025-Q2"
    resolution_worsen_factor: float = 1.8


PLANS = [
    # (name, tier, monthly_price_cents, unit_cost_cents)
    ("Starter Legacy", "smb", 4_900, 2_100),
    ("Starter", "smb", 5_900, 2_300),
    ("Growth", "mid", 24_900, 9_500),
    ("Scale", "mid", 49_900, 17_500),
    ("Enterprise", "enterprise", 199_900, 62_000),
]


def _lit(v) -> str:
    """Render a Python value as a DuckDB SQL literal.

    Generation writes tens of thousands of rows; DuckDB's parameter-binding
    path (executemany / `?` placeholders) is ~680x slower than a single
    inlined-literal INSERT, so we format values into text and execute once.
    All values here are generator-controlled (ints, floats, dates, quote-free
    identifiers); strings are still escaped defensively.
    """
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, date):
        return f"DATE '{v.isoformat()}'"
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _bulk_insert(con, table: str, rows: list[tuple], chunk: int = 5000) -> None:
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        values = ",".join("(" + ",".join(_lit(x) for x in r) + ")" for r in batch)
        con.execute(f"INSERT INTO {table} VALUES {values}")


def month_seq(start: str, n: int) -> list[str]:
    y, m = (int(x) for x in start.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def month_first_day(month: str) -> date:
    y, m = (int(x) for x in month.split("-"))
    return date(y, m, 1)


def quarter_of(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y}-Q{(m - 1) // 3 + 1}"


def generate(db_path: str | Path, params: PlantedParams | None = None) -> PlantedParams:
    """Generate the business into a fresh DuckDB file. Returns the params used."""
    p = params or PlantedParams()
    rng = random.Random(p.seed)
    months = month_seq(p.start_month, p.n_months)

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))

    con.execute(
        """
        CREATE TABLE plans (
            plan_id INTEGER PRIMARY KEY, name VARCHAR, tier VARCHAR,
            monthly_price_cents INTEGER, unit_cost_cents INTEGER);
        CREATE TABLE accounts (
            account_id INTEGER PRIMARY KEY, name VARCHAR, region VARCHAR,
            segment VARCHAR, signup_month VARCHAR);
        CREATE TABLE subscriptions (
            sub_id INTEGER PRIMARY KEY, account_id INTEGER, plan_id INTEGER,
            start_month VARCHAR, end_month VARCHAR);
        CREATE TABLE invoices (
            invoice_id INTEGER PRIMARY KEY, account_id INTEGER, plan_id INTEGER,
            month VARCHAR, amount_cents INTEGER, cost_cents INTEGER,
            issued_date DATE, paid_date DATE);
        CREATE TABLE support_tickets (
            ticket_id INTEGER PRIMARY KEY, account_id INTEGER,
            opened_date DATE, resolved_date DATE, severity VARCHAR);
        """
    )

    _bulk_insert(con, "plans", [(i + 1, *row) for i, row in enumerate(PLANS)])
    plan_by_tier: dict[str, list[int]] = {}
    for i, (_, tier, _, _) in enumerate(PLANS):
        plan_by_tier.setdefault(tier, []).append(i + 1)
    plan_price = {i + 1: PLANS[i][2] for i in range(len(PLANS))}
    plan_cost = {i + 1: PLANS[i][3] for i in range(len(PLANS))}
    plan_name = {i + 1: PLANS[i][0] for i in range(len(PLANS))}
    discontinued_id = next(k for k, v in plan_name.items() if v == p.discontinued_plan)

    # --- accounts -----------------------------------------------------------
    accounts = []
    for aid in range(1, p.n_accounts + 1):
        segment = rng.choices(SEGMENTS, weights=[0.55, 0.30, 0.15])[0]
        region = rng.choices(REGIONS, weights=[0.45, 0.35, 0.20])[0]
        signup = months[rng.randrange(0, max(1, p.n_months - 6))]
        accounts.append((aid, f"acct-{aid:05d}", region, segment, signup))
    _bulk_insert(con, "accounts", accounts)

    # --- lifecycle simulation ------------------------------------------------
    subs, invoices, tickets = [], [], []
    sub_id = inv_id = tik_id = 0
    # Planted events outside a short horizon simply never fire (len(months) is an
    # index no month reaches), keeping generation valid for any n_months.
    price_change_idx = (months.index(p.eu_price_change_month)
                        if p.eu_price_change_month in months else len(months))
    disc_cutoff_idx = (months.index(p.discontinued_after)
                       if p.discontinued_after in months else len(months))

    for aid, _, region, segment, signup in accounts:
        # pick a plan; discontinued plan only assignable before its cutoff
        candidates = list(plan_by_tier[segment])
        if months.index(signup) > disc_cutoff_idx:
            candidates = [c for c in candidates if c != discontinued_id]
        plan = rng.choice(candidates)

        active = True
        end_month = None
        unresolved = 0
        start_idx = months.index(signup)

        for mi in range(start_idx, p.n_months):
            month = months[mi]
            if not active:
                break

            # discontinued plan: forced migration (sub ends, new sub on Starter)
            if plan == discontinued_id and mi > disc_cutoff_idx:
                sub_id += 1
                subs.append((sub_id, aid, plan, signup, months[mi - 1] if mi else signup))
                plan = plan_by_tier["smb"][1]  # "Starter"
                signup = month
                start_idx = mi

            # invoice for the month
            price = plan_price[plan]
            cost = plan_cost[plan]
            if region == "EU" and mi >= price_change_idx:
                price = int(round(price * (1 + p.eu_price_increase)))
                cost = int(round(cost * (1 + p.eu_cost_increase)))
            issued = month_first_day(month) + timedelta(days=rng.randrange(0, 5))
            paid = None if rng.random() < 0.06 else issued + timedelta(days=rng.randrange(3, 40))
            inv_id += 1
            invoices.append((inv_id, aid, plan, month, price, cost, issued, paid))

            # support tickets (~0.35/month avg, enterprise slightly more)
            lam = 0.5 if segment == "enterprise" else 0.3
            n_new = 1 if rng.random() < lam else 0
            for _ in range(n_new):
                opened = month_first_day(month) + timedelta(days=rng.randrange(0, 27))
                worsen = quarter_of(month) == p.resolution_worsen_quarter
                base_days = rng.expovariate(1 / 6.0)
                if worsen:
                    base_days *= p.resolution_worsen_factor
                if rng.random() < 0.18:
                    resolved = None  # unresolved: the NULL trap
                    unresolved += 1
                else:
                    resolved = opened + timedelta(days=max(1, int(base_days)))
                sev = rng.choices(["low", "medium", "high"], weights=[0.5, 0.35, 0.15])[0]
                tik_id += 1
                tickets.append((tik_id, aid, opened, resolved, sev))

            # churn decision at month end
            churn_p = p.base_churn[segment]
            if segment == "enterprise" and unresolved > 2:
                churn_p *= p.ticket_churn_multiplier
            if rng.random() < churn_p:
                active = False
                end_month = month

        sub_id += 1
        subs.append((sub_id, aid, plan, signup, end_month))

    _bulk_insert(con, "subscriptions", subs)
    _bulk_insert(con, "invoices", invoices)
    _bulk_insert(con, "support_tickets", tickets)
    con.close()
    return p
