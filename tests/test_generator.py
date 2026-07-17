import duckdb

from harness.synth.generator import PlantedParams, generate, month_seq


def _q(db, sql, *args):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql, list(args)).fetchone()[0]
    finally:
        con.close()


def test_determinism(tmp_path):
    p = PlantedParams(seed=99, n_accounts=150, n_months=12)
    a, b = tmp_path / "a.duckdb", tmp_path / "b.duckdb"
    generate(a, p)
    generate(b, p)
    for sql in [
        "SELECT SUM(amount_cents) FROM invoices",
        "SELECT COUNT(*) FROM support_tickets",
        "SELECT COUNT(*) FROM subscriptions WHERE end_month IS NOT NULL",
    ]:
        assert _q(a, sql) == _q(b, sql)

    c = tmp_path / "c.duckdb"
    generate(c, PlantedParams(seed=100, n_accounts=150, n_months=12))
    assert _q(a, "SELECT SUM(amount_cents) FROM invoices") != _q(
        c, "SELECT SUM(amount_cents) FROM invoices")


def test_discontinued_plan_stops_invoicing(db_path, params):
    months = month_seq(params.start_month, params.n_months)
    cutoff = params.discontinued_after
    after = _q(db_path, """
        SELECT COUNT(*) FROM invoices i JOIN plans p USING (plan_id)
        WHERE p.name = ? AND i.month > ?""", params.discontinued_plan, cutoff)
    before = _q(db_path, """
        SELECT COUNT(*) FROM invoices i JOIN plans p USING (plan_id)
        WHERE p.name = ? AND i.month <= ?""", params.discontinued_plan, cutoff)
    assert after == 0
    assert before > 0
    assert cutoff in months


def test_eu_margin_drop_planted(db_path, params):
    months = month_seq(params.start_month, params.n_months)
    pci = months.index(params.eu_price_change_month)
    windows = {
        "before": months[pci - 3:pci],
        "after": months[pci:pci + 3],
    }
    margins = {}
    for name, ms in windows.items():
        placeholders = ",".join("?" * len(ms))
        margins[name] = _q(db_path, f"""
            SELECT 100.0 * (SUM(i.amount_cents) - SUM(i.cost_cents)) / SUM(i.amount_cents)
            FROM invoices i JOIN accounts a USING (account_id)
            WHERE a.region = 'EU' AND i.month IN ({placeholders})""", *ms)
    assert margins["before"] - margins["after"] >= 2.0  # planted multi-point drop


def test_resolution_worsens_in_planted_quarter(db_path):
    sql = """
        SELECT AVG(DATEDIFF('day', opened_date, resolved_date))
        FROM support_tickets
        WHERE resolved_date IS NOT NULL
          AND CAST(EXTRACT(year FROM opened_date) AS INT) = 2025
          AND CAST((EXTRACT(month FROM opened_date) - 1) // 3 + 1 AS INT) = ?"""
    q1, q2 = _q(db_path, sql, 1), _q(db_path, sql, 2)
    assert q2 > q1


def test_null_traps_exist(db_path):
    assert _q(db_path, "SELECT COUNT(*) FROM support_tickets WHERE resolved_date IS NULL") > 0
    assert _q(db_path, """
        SELECT COUNT(*) FROM accounts a
        WHERE NOT EXISTS (SELECT 1 FROM support_tickets t
                          WHERE t.account_id = a.account_id)""") > 0
