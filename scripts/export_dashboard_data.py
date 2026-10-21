"""
export_dashboard_data.py
Exports gold layer data as JSON for the GitHub Pages dashboard.
The dashboard (docs/index.html) reads these JSON files directly —
no server needed, works on GitHub Pages.

Run:
  python scripts/export_dashboard_data.py

Outputs to docs/data/ (committed alongside the HTML).
"""

import duckdb
import json
import os

DB_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'platform.duckdb')
OUT_DIR  = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data')

os.makedirs(OUT_DIR, exist_ok=True)

def export(con, query, filename):
    rows = con.execute(query).fetchall()
    cols = [d[0] for d in con.description]
    data = [dict(zip(cols, row)) for row in rows]
    # Convert non-serialisable types
    for row in data:
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
            elif v is None:
                row[k] = None
    path = os.path.join(OUT_DIR, filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Exported {filename}: {len(data)} rows")

def main():
    print("=== Exporting dashboard data to JSON ===")
    con = duckdb.connect(DB_PATH, read_only=True)

    export(con,
        "SELECT month, SUM(total_invoiced) AS total_invoiced, "
        "SUM(total_paid) AS total_paid "
        "FROM gold.monthly_revenue GROUP BY month ORDER BY month",
        'monthly_revenue.json')

    export(con,
        "SELECT customer_name, total_invoiced, paid_amount, "
        "total_orders, sla_breaches, health_score "
        "FROM gold.customer_health ORDER BY total_invoiced DESC",
        'customer_health.json')

    export(con,
        "SELECT region, total_orders, on_time, late, on_time_rate_pct "
        "FROM gold.sla_by_region ORDER BY on_time_rate_pct DESC",
        'sla_by_region.json')

    export(con,
        "SELECT product_id, total_invoiced, invoice_count "
        "FROM gold.product_revenue ORDER BY total_invoiced DESC",
        'product_revenue.json')

    export(con,
        "SELECT total_revenue_invoiced, total_revenue_paid, "
        "avg_invoice_value, total_invoices, payment_rate_pct "
        "FROM gold.operational_kpis",
        'kpis.json')

    con.close()
    print("Done. JSON files written to docs/data/")

if __name__ == '__main__':
    main()
