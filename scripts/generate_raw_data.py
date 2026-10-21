"""
generate_raw_data.py
Generates realistic synthetic raw data for three source systems:
  - finance_system: invoices and revenue records
  - ops_system: order fulfilment and delivery records
  - sales_system: sales transactions and deal records

Deliberately introduces the kinds of inconsistencies found in real multi-system
environments: different date formats, different customer ID conventions, duplicate
records, missing values, and conflicting revenue figures — exactly the problems
this pipeline is built to resolve.
"""

import csv
import random
import os
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Shared reference data
CUSTOMERS = [
    ('C001', 'Greenwave Energy', 'Energy'),
    ('C002', 'UrbanMobility Co', 'Transport'),
    ('C003', 'NovaTech Systems', 'Technology'),
    ('C004', 'ClearPath Logistics', 'Logistics'),
    ('C005', 'Meridian Retail', 'Retail'),
    ('C006', 'Apex Manufacturing', 'Manufacturing'),
    ('C007', 'Solaris Renewables', 'Energy'),
    ('C008', 'BlueStar Finance', 'Financial Services'),
]

PRODUCTS = [
    ('P001', 'Platform Licence', 1200.00),
    ('P002', 'API Integration', 800.00),
    ('P003', 'Data Analytics Module', 1500.00),
    ('P004', 'Support Package', 400.00),
    ('P005', 'Onboarding Services', 2000.00),
]

REGIONS = ['North', 'South', 'East', 'West', 'Central']

def random_date(start_year=2023, end_year=2024):
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


# ─────────────────────────────────────────
# 1. FINANCE SYSTEM
# Invoices raised by finance. Date format: DD/MM/YYYY.
# Customer IDs prefixed with 'FIN-'. Some invoices duplicated (billing error).
# Some amounts differ slightly from sales system (rounding, FX adjustments).
# ─────────────────────────────────────────
def generate_finance_data(n=120):
    rows = []
    for i in range(1, n + 1):
        cust = random.choice(CUSTOMERS)
        prod = random.choice(PRODUCTS)
        qty = random.randint(1, 5)
        unit_price = prod[2] * random.uniform(0.95, 1.05)  # slight price variance
        amount = round(unit_price * qty, 2)
        inv_date = random_date()
        paid = random.choice(['Yes', 'Yes', 'Yes', 'No', 'Pending'])
        rows.append({
            'invoice_id': f'INV-{i:04d}',
            'customer_id': f'FIN-{cust[0]}',       # finance uses FIN- prefix
            'customer_name': cust[1],
            'product_id': prod[0],
            'quantity': qty,
            'unit_price': unit_price,
            'total_amount': amount,
            'invoice_date': inv_date.strftime('%d/%m/%Y'),  # DD/MM/YYYY format
            'payment_status': paid,
            'region': random.choice(REGIONS),
        })

    # Introduce ~5 duplicate invoices (same invoice_id, slightly different amount)
    for _ in range(5):
        original = random.choice(rows[:80])
        dup = original.copy()
        dup['total_amount'] = round(original['total_amount'] * 1.002, 2)
        rows.append(dup)

    # Introduce ~3 rows with missing customer_name
    for _ in range(3):
        rows[random.randint(0, n-1)]['customer_name'] = ''

    with open(os.path.join(OUTPUT_DIR, 'finance_invoices.csv'), 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"  finance_invoices.csv: {len(rows)} rows")


# ─────────────────────────────────────────
# 2. OPERATIONS SYSTEM
# Order fulfilment records. Date format: YYYY-MM-DD (ISO).
# Customer IDs use raw CXxx format. SLA breaches tracked.
# ─────────────────────────────────────────
def generate_ops_data(n=130):
    rows = []
    for i in range(1, n + 1):
        cust = random.choice(CUSTOMERS)
        prod = random.choice(PRODUCTS)
        qty = random.randint(1, 5)
        order_date = random_date()
        sla_days = random.randint(1, 5)
        delivered_days = sla_days + random.randint(-1, 3)
        delivered_days = max(delivered_days, 1)
        delivery_date = order_date + timedelta(days=delivered_days)
        sla_met = 'Yes' if delivered_days <= sla_days else 'No'
        status = random.choice(['Delivered', 'Delivered', 'Delivered', 'In Transit', 'Cancelled'])
        rows.append({
            'order_id': f'ORD-{i:04d}',
            'customer_id': cust[0],                # raw CXxx — no prefix
            'product_id': prod[0],
            'quantity': qty,
            'order_date': order_date.strftime('%Y-%m-%d'),   # ISO format
            'delivery_date': delivery_date.strftime('%Y-%m-%d'),
            'sla_days': sla_days,
            'actual_days': delivered_days,
            'sla_met': sla_met,
            'status': status,
            'region': random.choice(REGIONS),
        })

    # ~4 rows with null delivery_date (orders still in transit)
    for _ in range(4):
        rows[random.randint(80, n-1)]['delivery_date'] = ''
        rows[random.randint(80, n-1)]['sla_met'] = ''

    with open(os.path.join(OUTPUT_DIR, 'ops_orders.csv'), 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"  ops_orders.csv: {len(rows)} rows")


# ─────────────────────────────────────────
# 3. SALES SYSTEM
# CRM deal records. Date format: MM-DD-YYYY (US format).
# Customer IDs prefixed with 'SALES-'. Revenue figures are contract values
# (may differ from invoiced amounts in finance system).
# ─────────────────────────────────────────
def generate_sales_data(n=100):
    rows = []
    stages = ['Closed Won', 'Closed Won', 'Closed Won', 'Closed Lost', 'Negotiation']
    for i in range(1, n + 1):
        cust = random.choice(CUSTOMERS)
        prod = random.choice(PRODUCTS)
        qty = random.randint(1, 5)
        contract_value = round(prod[2] * qty * random.uniform(0.9, 1.1), 2)
        close_date = random_date()
        stage = random.choice(stages)
        owner = random.choice(['Alice M', 'Ben T', 'Clara O', 'David N', 'Eve S'])
        rows.append({
            'deal_id': f'DEAL-{i:04d}',
            'customer_id': f'SALES-{cust[0]}',     # SALES- prefix
            'customer_name': cust[1],
            'product_id': prod[0],
            'quantity': qty,
            'contract_value': contract_value,
            'close_date': close_date.strftime('%m-%d-%Y'),  # US MM-DD-YYYY
            'deal_stage': stage,
            'sales_owner': owner,
            'industry': cust[2],
            'region': random.choice(REGIONS),
        })

    # ~3 rows with missing industry (data entry gaps)
    for _ in range(3):
        rows[random.randint(0, n-1)]['industry'] = ''

    with open(os.path.join(OUTPUT_DIR, 'sales_deals.csv'), 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"  sales_deals.csv: {len(rows)} rows")


if __name__ == '__main__':
    print("Generating synthetic raw data...")
    generate_finance_data()
    generate_ops_data()
    generate_sales_data()
    print("Done. Raw files written to data/raw/")
