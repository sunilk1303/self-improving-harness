"""Golden question/answer emission — ground truth by construction.

Each template carries hand-written, trusted reference SQL (or a small
computation over such SQL). At emission time the reference runs against the
freshly generated warehouse, so every golden answer is exact for THIS seed.
Rotating the private slice = regenerating with a new seed.

Strata: single_table | multi_join | federated | narrative.
Families: revenue | churn | margin.
Tripwires are questions whose plausible-sounding answer is wrong unless the
data is actually queried (discontinued plan, sign-flip, NULL trap).

The public/private split is a deterministic hash of (qid, salt): same seed and
salt always produce the same split, and the private slice is disjoint by
construction. (Template-level holdout arrives with E1.)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from .generator import PlantedParams, month_seq

PRIVATE_FRACTION = 0.25
SPLIT_SALT = "e0-split-v1"


@dataclass
class Question:
    qid: str
    family: str          # revenue | churn | margin
    stratum: str         # single_table | multi_join | federated | narrative
    text: str
    answer_type: str     # scalar | table | facts
    expected: object     # float | list[list] | dict[str, float|str]
    tripwire: bool = False
    slice: str = "public"
    meta: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _scalar(con, sql: str, *params) -> float:
    row = con.execute(sql, params).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _split_for(qid: str) -> str:
    h = hashlib.sha256(f"{SPLIT_SALT}:{qid}".encode()).hexdigest()
    return "private" if int(h[:8], 16) / 0xFFFFFFFF < PRIVATE_FRACTION else "public"


def emit(db_path: str | Path, params: PlantedParams) -> list[Question]:
    con = duckdb.connect(str(db_path), read_only=True)
    months = month_seq(params.start_month, params.n_months)
    # skip the ramp-up months where cohorts are tiny
    active_months = months[3:]
    questions: list[Question] = []

    def add(q: Question) -> None:
        q.slice = _split_for(q.qid)
        questions.append(q)

    # ---- revenue -----------------------------------------------------------
    for m in active_months:
        v = _scalar(con, "SELECT SUM(amount_cents)/100.0 FROM invoices WHERE month = ?", m)
        add(Question(f"R1-{m}", "revenue", "single_table",
                     f"What was total invoiced revenue in USD in {m}?", "scalar", v))

    for m in active_months[::2]:
        for seg in ["smb", "mid", "enterprise"]:
            for reg in ["NA", "EU"]:
                v = _scalar(con, """
                    SELECT COALESCE(SUM(i.amount_cents), 0)/100.0
                    FROM invoices i JOIN accounts a USING (account_id)
                    WHERE i.month = ? AND a.segment = ? AND a.region = ?""", m, seg, reg)
                add(Question(f"R2-{m}-{seg}-{reg}", "revenue", "multi_join",
                             f"What was total invoiced revenue in USD from {seg} accounts "
                             f"in {reg} in {m}?", "scalar", v))

    for year in sorted({m[:4] for m in active_months}):
        row = con.execute("""
            SELECT p.name, SUM(i.amount_cents)/100.0 AS rev
            FROM invoices i JOIN plans p USING (plan_id)
            WHERE i.month LIKE ? GROUP BY 1 ORDER BY rev DESC LIMIT 1""",
            [f"{year}-%"]).fetchone()
        add(Question(f"R3-{year}", "revenue", "multi_join",
                     f"Which plan generated the highest invoiced revenue in {year}, "
                     f"and how much (USD)?", "table", [[row[0], float(row[1])]]))

    # narrative: EU revenue around the planted price change
    pc = params.eu_price_change_month
    pci = months.index(pc)
    before, after = months[pci - 3:pci], months[pci:pci + 3]
    eu_rev = lambda ms: _scalar(con, f"""
        SELECT SUM(i.amount_cents)/100.0 FROM invoices i
        JOIN accounts a USING (account_id)
        WHERE a.region = 'EU' AND i.month IN ({','.join('?' * len(ms))})""", *ms)
    rb, ra = eu_rev(before), eu_rev(after)
    add(Question("R4-eu-price-change", "revenue", "narrative",
                 f"Compare EU invoiced revenue in the three months from {pc} against the "
                 f"three months before. Did it increase or decrease, and by what percent?",
                 "facts", {"direction": "increased" if ra > rb else "decreased",
                           "pct_change": round((ra - rb) / rb * 100, 2)}))

    # ---- churn -------------------------------------------------------------
    for m in active_months:
        v = _scalar(con, "SELECT COUNT(*) FROM subscriptions WHERE end_month = ?", m)
        add(Question(f"C1-{m}", "churn", "single_table",
                     f"How many subscriptions ended in {m}?", "scalar", v))

    churn_rate_sql = """
        WITH active_at_start AS (
            SELECT DISTINCT a.account_id FROM accounts a
            JOIN subscriptions s USING (account_id)
            WHERE a.segment = ? AND s.start_month <= ?
              AND (s.end_month IS NULL OR s.end_month >= ?)),
        churned AS (
            SELECT DISTINCT a.account_id FROM accounts a
            JOIN subscriptions s USING (account_id)
            WHERE a.segment = ? AND s.end_month = ?
              AND NOT EXISTS (SELECT 1 FROM subscriptions s2
                              WHERE s2.account_id = a.account_id
                                AND (s2.end_month IS NULL OR s2.end_month > ?)))
        SELECT CASE WHEN (SELECT COUNT(*) FROM active_at_start) = 0 THEN 0
               ELSE 100.0 * (SELECT COUNT(*) FROM churned)
                    / (SELECT COUNT(*) FROM active_at_start) END"""
    for m in active_months[::3]:
        for seg in ["smb", "enterprise"]:
            v = _scalar(con, churn_rate_sql, seg, m, m, seg, m, m)
            add(Question(f"C2-{m}-{seg}", "churn", "multi_join",
                         f"What was the account churn rate (percent) for {seg} accounts "
                         f"in {m}? Churn = account's last subscription ended that month; "
                         f"denominator = accounts active at the start of the month.",
                         "scalar", v))

    v = _scalar(con, """
        SELECT COUNT(DISTINCT a.account_id)
        FROM accounts a JOIN subscriptions s USING (account_id)
        WHERE a.segment = 'enterprise' AND s.end_month IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM subscriptions s2
                          WHERE s2.account_id = a.account_id AND s2.end_month IS NULL)
          AND (SELECT COUNT(*) FROM support_tickets t
               WHERE t.account_id = a.account_id AND t.resolved_date IS NULL) > 2""")
    add(Question("C3-ent-unresolved", "churn", "multi_join",
                 "How many churned enterprise accounts had more than 2 unresolved "
                 "support tickets?", "scalar", v))

    # narrative: which segment churns most (planted: smb)
    rows = con.execute("""
        SELECT a.segment,
               100.0 * COUNT(DISTINCT CASE WHEN s.end_month IS NOT NULL THEN a.account_id END)
                     / COUNT(DISTINCT a.account_id) AS churned_pct
        FROM accounts a JOIN subscriptions s USING (account_id)
        GROUP BY 1 ORDER BY churned_pct DESC""").fetchall()
    add(Question("C4-segment-churn", "churn", "narrative",
                 "Which segment has the highest share of accounts that have churned, "
                 "and what is that share in percent?",
                 "facts", {"segment": rows[0][0], "churned_pct": round(float(rows[0][1]), 2)}))

    # ---- margin ------------------------------------------------------------
    for m in active_months[::2]:
        v = _scalar(con, """
            SELECT 100.0 * (SUM(amount_cents) - SUM(cost_cents)) / SUM(amount_cents)
            FROM invoices WHERE month = ?""", m)
        add(Question(f"M1-{m}", "margin", "single_table",
                     f"What was gross margin (percent of invoiced revenue) in {m}?",
                     "scalar", v))

    for m in months[pci:pci + 6:2]:
        row = con.execute("""
            SELECT a.region,
                   100.0 * (SUM(i.amount_cents) - SUM(i.cost_cents)) / SUM(i.amount_cents) AS gm
            FROM invoices i JOIN accounts a USING (account_id)
            WHERE i.month = ? GROUP BY 1 ORDER BY gm ASC LIMIT 1""", [m]).fetchone()
        add(Question(f"M2-{m}", "margin", "multi_join",
                     f"Which region had the lowest gross margin in {m}, and what was it "
                     f"(percent)?", "table", [[row[0], round(float(row[1]), 4)]]))

    # federated: stale pricing doc vs actual EU enterprise invoicing
    m_after = months[pci + 1]
    inv_avg = _scalar(con, """
        SELECT AVG(i.amount_cents)/100.0 FROM invoices i
        JOIN accounts a USING (account_id) JOIN plans p USING (plan_id)
        WHERE a.region = 'EU' AND p.name = 'Enterprise' AND i.month = ?""", m_after)
    add(Question("M3-doc-vs-invoice", "margin", "federated",
                 f"According to the pricing policy document, what is the Enterprise plan's "
                 f"monthly list price, and does it match the average invoiced amount for EU "
                 f"Enterprise-plan accounts in {m_after}? Give both numbers.",
                 "facts", {"doc_price": 1999.00, "invoiced_avg": round(inv_avg, 2),
                           "match": "no"}))

    # ---- tripwires ----------------------------------------------------------
    disc_after_idx = months.index(params.discontinued_after)
    for m in months[disc_after_idx + 2:disc_after_idx + 8:2]:
        v = _scalar(con, """
            SELECT COALESCE(SUM(i.amount_cents), 0)/100.0 FROM invoices i
            JOIN plans p USING (plan_id) WHERE p.name = ? AND i.month = ?""",
            params.discontinued_plan, m)
        add(Question(f"T1-{m}", "revenue", "single_table",
                     f"What was invoiced revenue in USD from the '{params.discontinued_plan}' "
                     f"plan in {m}?", "scalar", v, tripwire=True,
                     meta={"trap": "discontinued-plan; correct answer is 0"}))

    res_days_sql = """
        SELECT AVG(DATEDIFF('day', opened_date, resolved_date))
        FROM support_tickets
        WHERE resolved_date IS NOT NULL
          AND (CAST(EXTRACT(year FROM opened_date) AS INT) = ?
               AND CAST((EXTRACT(month FROM opened_date) - 1) // 3 + 1 AS INT) = ?)"""
    q1 = _scalar(con, res_days_sql, 2025, 1)
    q2 = _scalar(con, res_days_sql, 2025, 2)
    add(Question("T2-resolution-signflip", "churn", "narrative",
                 "Did average support-ticket resolution time improve or worsen in 2025-Q2 "
                 "compared with 2025-Q1? Give both averages in days.",
                 "facts", {"direction": "worsened" if q2 > q1 else "improved",
                           "q1_days": round(q1, 2), "q2_days": round(q2, 2)},
                 tripwire=True,
                 meta={"trap": "product-notes.md implies improvement; data worsens"}))

    v = _scalar(con, """
        SELECT COUNT(*) FROM accounts a
        WHERE NOT EXISTS (SELECT 1 FROM support_tickets t
                          WHERE t.account_id = a.account_id)""")
    add(Question("T3-no-tickets", "churn", "single_table",
                 "How many accounts have never opened a support ticket?", "scalar", v,
                 tripwire=True, meta={"trap": "naive NOT IN + NULL returns wrong count"}))

    con.close()
    return questions


def write_slices(questions: list[Question], out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = {"public": 0, "private": 0}
    handles = {s: open(out / f"{s}.jsonl", "w", encoding="utf-8") for s in counts}
    try:
        for q in questions:
            handles[q.slice].write(q.to_json() + "\n")
            counts[q.slice] += 1
    finally:
        for h in handles.values():
            h.close()
    return counts


def load_slice(path: str | Path) -> list[Question]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out.append(Question(**d))
    return out
