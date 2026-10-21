"""
test_quality.py  — Automated Data Quality Test Suite
======================================================
Runs data quality checks across all three pipeline layers (bronze, silver, gold).
Each test is self-documenting: it explains what it checks, why it matters,
and what failure means operationally.

Tests are grouped by layer and type:
  - Completeness:    required fields are not null or empty
  - Uniqueness:      primary keys have no duplicates
  - Reconciliation:  row counts and totals are consistent across layers
  - Validity:        values fall within expected ranges or sets
  - Referential:     keys join cleanly across tables

Run:
  python -m pytest tests/test_quality.py -v

Or directly:
  python tests/test_quality.py
"""

import duckdb
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'platform.duckdb')

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

results = []

def check(name, passed, detail='', warn_only=False):
    status = PASS if passed else (WARN if warn_only else FAIL)
    label  = 'PASS' if passed else ('WARN' if warn_only else 'FAIL')
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")
    results.append({'name': name, 'passed': passed, 'warn': warn_only, 'detail': detail})
    return passed


def run_tests():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run scripts/ingest.py and scripts/transform.py first.")
        sys.exit(1)

    con = duckdb.connect(DB_PATH, read_only=True)
    failures = 0

    # ─────────────────────────────────────────
    # BRONZE LAYER CHECKS
    # These verify the raw ingestion is complete and nothing was silently dropped.
    # ─────────────────────────────────────────
    print("\n=== BRONZE LAYER ===")

    # B1: Row count thresholds — raw data must be present
    fin_count  = con.execute("SELECT COUNT(*) FROM bronze.finance_invoices").fetchone()[0]
    ops_count  = con.execute("SELECT COUNT(*) FROM bronze.ops_orders").fetchone()[0]
    sales_count = con.execute("SELECT COUNT(*) FROM bronze.sales_deals").fetchone()[0]

    check("B1: Finance invoices loaded (>=100 rows)", fin_count >= 100,
          f"Actual: {fin_count} rows")
    check("B2: Ops orders loaded (>=100 rows)", ops_count >= 100,
          f"Actual: {ops_count} rows")
    check("B3: Sales deals loaded (>=50 rows)", sales_count >= 50,
          f"Actual: {sales_count} rows")

    # B4: All bronze tables have the ingestion metadata columns
    for tbl in ['finance_invoices', 'ops_orders', 'sales_deals']:
        cols = [r[0] for r in con.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema='bronze' AND table_name='{tbl}'"
        ).fetchall()]
        has_meta = '_source_system' in cols and '_loaded_at' in cols
        check(f"B4: bronze.{tbl} has ingestion metadata", has_meta,
              f"Columns found: {[c for c in cols if c.startswith('_')]}")

    # ─────────────────────────────────────────
    # SILVER LAYER CHECKS
    # These verify that cleaning and standardisation worked correctly.
    # Failures here mean the pipeline produced wrong or unusable data.
    # ─────────────────────────────────────────
    print("\n=== SILVER LAYER ===")

    # S1: Deduplication — silver should have fewer rows than bronze (duplicates removed)
    sil_fin = con.execute("SELECT COUNT(*) FROM silver.finance_invoices").fetchone()[0]
    check("S1: Finance deduplication (silver < bronze)",
          sil_fin < fin_count,
          f"Bronze: {fin_count}, Silver: {sil_fin}, removed: {fin_count - sil_fin}")

    # S2: No duplicate invoice_ids in silver
    dup_inv = con.execute(
        "SELECT COUNT(*) FROM (SELECT invoice_id, COUNT(*) c "
        "FROM silver.finance_invoices GROUP BY 1 HAVING c > 1)"
    ).fetchone()[0]
    check("S2: No duplicate invoice_ids in silver.finance_invoices",
          dup_inv == 0, f"Duplicates found: {dup_inv}")
    if dup_inv > 0: failures += 1

    # S3: No null invoice_dates after date parsing
    null_dates = con.execute(
        "SELECT COUNT(*) FROM silver.finance_invoices WHERE invoice_date IS NULL"
    ).fetchone()[0]
    check("S3: No null invoice_dates after DD/MM/YYYY parsing",
          null_dates == 0, f"Null dates: {null_dates}")
    if null_dates > 0: failures += 1

    # S4: Customer IDs stripped of system prefixes
    bad_fin_ids = con.execute(
        "SELECT COUNT(*) FROM silver.finance_invoices WHERE customer_id LIKE 'FIN-%'"
    ).fetchone()[0]
    bad_sales_ids = con.execute(
        "SELECT COUNT(*) FROM silver.sales_deals WHERE customer_id LIKE 'SALES-%'"
    ).fetchone()[0]
    check("S4: Finance customer_ids have no FIN- prefix",  bad_fin_ids == 0,
          f"Rows still with prefix: {bad_fin_ids}")
    check("S5: Sales customer_ids have no SALES- prefix", bad_sales_ids == 0,
          f"Rows still with prefix: {bad_sales_ids}")
    if bad_fin_ids + bad_sales_ids > 0: failures += 1

    # S5: Payment status only contains known values
    bad_status = con.execute(
        "SELECT COUNT(*) FROM silver.finance_invoices "
        "WHERE payment_status NOT IN ('Paid','Unpaid','Pending','Unknown')"
    ).fetchone()[0]
    check("S6: payment_status contains only valid values", bad_status == 0,
          f"Invalid values: {bad_status}")
    if bad_status > 0: failures += 1

    # S6: No negative amounts
    neg_amounts = con.execute(
        "SELECT COUNT(*) FROM silver.finance_invoices WHERE total_amount < 0"
    ).fetchone()[0]
    check("S7: No negative total_amount values", neg_amounts == 0,
          f"Negative amounts: {neg_amounts}")
    if neg_amounts > 0: failures += 1

    # S7: Ops orders — null delivery_date only for non-delivered orders
    bad_nulls = con.execute(
        "SELECT COUNT(*) FROM silver.ops_orders "
        "WHERE delivery_date IS NULL AND status = 'Delivered'"
    ).fetchone()[0]
    check("S8: No null delivery_date for Delivered orders", bad_nulls == 0,
          f"Delivered orders with null date: {bad_nulls}")
    if bad_nulls > 0: failures += 1

    # S8: Sales close_date successfully parsed from MM-DD-YYYY
    null_close = con.execute(
        "SELECT COUNT(*) FROM silver.sales_deals WHERE close_date IS NULL"
    ).fetchone()[0]
    check("S9: No null close_date after MM-DD-YYYY parsing", null_close == 0,
          f"Null close dates: {null_close}")
    if null_close > 0: failures += 1

    # ─────────────────────────────────────────
    # GOLD LAYER CHECKS
    # These verify that the business metrics are correct and trustworthy.
    # Failures here mean dashboards and reports will show wrong numbers.
    # ─────────────────────────────────────────
    print("\n=== GOLD LAYER ===")

    # G1: All 5 gold tables exist and are non-empty
    gold_tables = ['monthly_revenue', 'customer_health', 'operational_kpis',
                   'product_revenue', 'sla_by_region']
    for t in gold_tables:
        count = con.execute(f"SELECT COUNT(*) FROM gold.{t}").fetchone()[0]
        ok = check(f"G1: gold.{t} exists and is non-empty", count > 0,
                   f"Rows: {count}")
        if not ok: failures += 1

    # G2: operational_kpis has exactly 1 row (it's a summary)
    kpi_rows = con.execute("SELECT COUNT(*) FROM gold.operational_kpis").fetchone()[0]
    check("G2: gold.operational_kpis has exactly 1 row", kpi_rows == 1,
          f"Rows: {kpi_rows}")
    if kpi_rows != 1: failures += 1

    # G3: Payment rate is between 0 and 100
    rate = con.execute("SELECT payment_rate_pct FROM gold.operational_kpis").fetchone()[0]
    check("G3: payment_rate_pct is between 0 and 100", 0 <= (rate or 0) <= 100,
          f"Value: {rate}%")
    if not (0 <= (rate or 0) <= 100): failures += 1

    # G4: Revenue reconciliation — gold total_invoiced should match silver
    gold_rev = con.execute(
        "SELECT total_revenue_invoiced FROM gold.operational_kpis"
    ).fetchone()[0]
    silver_rev = con.execute(
        "SELECT ROUND(SUM(total_amount), 0) FROM silver.finance_invoices "
        "WHERE payment_status IN ('Paid','Pending')"
    ).fetchone()[0]
    recon_ok = abs((gold_rev or 0) - (silver_rev or 0)) < 1.0
    check("G4: Gold revenue reconciles with silver (tolerance < £1)",
          recon_ok,
          f"Gold: £{gold_rev:,.0f}, Silver: £{silver_rev:,.0f}, diff: £{abs((gold_rev or 0)-(silver_rev or 0)):.2f}")
    if not recon_ok: failures += 1

    # G5: All 8 customers appear in customer_health
    gold_custs = con.execute("SELECT COUNT(*) FROM gold.customer_health").fetchone()[0]
    check("G5: All customers present in gold.customer_health", gold_custs >= 8,
          f"Customers in gold: {gold_custs}")

    # G6: SLA on_time_rate_pct between 0 and 100 for all regions
    bad_sla = con.execute(
        "SELECT COUNT(*) FROM gold.sla_by_region "
        "WHERE on_time_rate_pct < 0 OR on_time_rate_pct > 100"
    ).fetchone()[0]
    check("G6: SLA on_time_rate_pct is 0-100 for all regions", bad_sla == 0,
          f"Out-of-range values: {bad_sla}")
    if bad_sla > 0: failures += 1

    # G7: No null health_scores in customer_health
    null_hs = con.execute(
        "SELECT COUNT(*) FROM gold.customer_health WHERE health_score IS NULL"
    ).fetchone()[0]
    check("G7: No null health_scores in gold.customer_health", null_hs == 0,
          f"Null health_scores: {null_hs}", warn_only=True)

    con.close()

    # ─────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────
    total  = len(results)
    passed = sum(1 for r in results if r['passed'])
    warned = sum(1 for r in results if not r['passed'] and r['warn'])
    failed = sum(1 for r in results if not r['passed'] and not r['warn'])

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed | {warned} warnings | {failed} failures")
    if failed == 0:
        print("All critical checks passed. Pipeline data is trustworthy.")
    else:
        print(f"CRITICAL: {failed} check(s) failed. Investigate before using gold data.")
    print('='*50)

    return failed


if __name__ == '__main__':
    failures = run_tests()
    sys.exit(failures)
