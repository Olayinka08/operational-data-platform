"""
ingest.py  — Bronze Layer Ingestion
====================================
Reads the three raw CSV source files and loads them into DuckDB as bronze
(raw, unmodified) tables. This layer preserves source data exactly as received,
with only the addition of ingestion metadata (loaded_at, source_system).

Bronze tables created:
  bronze.finance_invoices
  bronze.ops_orders
  bronze.sales_deals

Run:
  python scripts/ingest.py

The DuckDB database file is written to data/processed/platform.duckdb.
"""

import duckdb
import pandas as pd
import os
from datetime import datetime, timezone

RAW_DIR    = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')
PROC_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
DB_PATH    = os.path.join(PROC_DIR, 'platform.duckdb')

os.makedirs(PROC_DIR, exist_ok=True)

SOURCES = {
    'finance_invoices': 'finance',
    'ops_orders':       'ops',
    'sales_deals':      'sales',
}

def load_csv(filename):
    path = os.path.join(RAW_DIR, f'{filename}.csv')
    df = pd.read_csv(path, dtype=str)          # read everything as string at bronze
    df['_source_system'] = SOURCES[filename]
    df['_loaded_at']     = datetime.now(timezone.utc).isoformat()
    df['_row_count']     = len(df)
    print(f"  Loaded {filename}: {len(df)} rows")
    return df

def main():
    print("=== Bronze Layer Ingestion ===")
    print(f"Target database: {DB_PATH}")

    con = duckdb.connect(DB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    for table_name in SOURCES:
        df = load_csv(table_name)
        full_name = f'bronze.{table_name}'
        con.execute(f"DROP TABLE IF EXISTS {full_name}")
        con.execute(f"CREATE TABLE {full_name} AS SELECT * FROM df")
        count = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
        print(f"  -> bronze.{table_name}: {count} rows committed")

    # Ingestion log table
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze.ingestion_log (
            run_at      TEXT,
            table_name  TEXT,
            row_count   INTEGER
        )
    """)
    run_at = datetime.now(timezone.utc).isoformat()
    for table_name in SOURCES:
        count = con.execute(f"SELECT COUNT(*) FROM bronze.{table_name}").fetchone()[0]
        con.execute("INSERT INTO bronze.ingestion_log VALUES (?, ?, ?)", [run_at, table_name, count])

    con.close()
    print("\nBronze ingestion complete.")
    print("Tables: bronze.finance_invoices | bronze.ops_orders | bronze.sales_deals")

if __name__ == '__main__':
    main()
