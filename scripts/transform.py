"""
transform.py  — Silver and Gold Transformation Layer
======================================================
Reads SQL transformation files and executes them against the DuckDB database
to build:
  Silver layer: cleaned, standardised, type-cast versions of each source table
  Gold layer:   single-definition business metrics joining across all systems

Architecture:
  bronze.*  ->  silver.*  ->  gold.*

Run:
  python scripts/transform.py

Requires ingest.py to have run first.
"""

import duckdb
import os

DB_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'platform.duckdb')
SQL_DIR  = os.path.join(os.path.dirname(__file__), '..', 'sql')

SILVER_SCRIPTS = [
    'silver_finance.sql',
    'silver_ops.sql',
    'silver_sales.sql',
]

GOLD_SCRIPTS = [
    'gold_metrics.sql',
]

def run_sql_file(con, filename):
    path = os.path.join(SQL_DIR, filename)
    with open(path, 'r') as f:
        sql = f.read()
    # Split on semicolons to execute statement by statement
    statements = [s.strip() for s in sql.split(';') if s.strip()]
    for stmt in statements:
        con.execute(stmt)
    print(f"  Executed: {filename} ({len(statements)} statements)")

def summarise_layer(con, schema):
    tables = con.execute(
        f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}'"
    ).fetchall()
    for (t,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {schema}.{t}").fetchone()[0]
        print(f"    {schema}.{t}: {count} rows")

def main():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run scripts/ingest.py first."
        )

    print("=== Silver + Gold Transformation ===")
    con = duckdb.connect(DB_PATH)

    # Create schemas
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")

    print("\n-- Silver layer --")
    for script in SILVER_SCRIPTS:
        run_sql_file(con, script)
    summarise_layer(con, 'silver')

    print("\n-- Gold layer --")
    for script in GOLD_SCRIPTS:
        run_sql_file(con, script)
    summarise_layer(con, 'gold')

    # Export gold tables to CSV for dashboard use
    export_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
    gold_tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
    ).fetchall()

    print("\n-- Exporting gold tables to CSV --")
    for (t,) in gold_tables:
        out_path = os.path.join(export_dir, f'gold_{t}.csv')
        con.execute(f"COPY gold.{t} TO '{out_path}' (HEADER, DELIMITER ',')")
        print(f"  Exported: gold_{t}.csv")

    con.close()
    print("\nTransformation complete.")
    print("Layers: bronze -> silver -> gold")

if __name__ == '__main__':
    main()
