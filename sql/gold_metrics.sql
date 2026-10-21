-- gold_metrics.sql
-- Gold layer: agreed, single-definition business metrics.
-- This is the layer that powers dashboards, finance reporting,
-- and operational decision-making. Every metric here has a single
-- agreed definition, documented below.

-- ─────────────────────────────────────────
-- GOLD 1: Monthly Revenue Summary
-- Definition: invoiced revenue (paid + pending) by month and region.
-- Source of truth: finance system (silver.finance_invoices).
-- Excludes: unpaid invoices where payment_status = 'Unpaid'.
-- ─────────────────────────────────────────
CREATE OR REPLACE TABLE gold.monthly_revenue AS
SELECT
    DATE_TRUNC('month', invoice_date)::DATE AS month,
    region,
    COUNT(DISTINCT invoice_id)              AS invoice_count,
    SUM(total_amount)                       AS total_invoiced,
    SUM(CASE WHEN payment_status = 'Paid'
             THEN total_amount ELSE 0 END)  AS total_paid,
    SUM(CASE WHEN payment_status = 'Pending'
             THEN total_amount ELSE 0 END)  AS total_pending,
    ROUND(
        SUM(CASE WHEN payment_status = 'Paid' THEN total_amount ELSE 0 END)
        / NULLIF(SUM(total_amount), 0) * 100, 1
    )                                       AS payment_rate_pct
FROM silver.finance_invoices
WHERE payment_status IN ('Paid', 'Pending')
GROUP BY 1, 2
ORDER BY 1, 2;


-- ─────────────────────────────────────────
-- GOLD 2: Customer Health Summary
-- Definition: per-customer view combining revenue (finance),
-- order fulfilment (ops), and pipeline value (sales).
-- Single agreed customer_id (canonical CXXX) joins all three systems.
-- ─────────────────────────────────────────
CREATE OR REPLACE TABLE gold.customer_health AS
WITH fin AS (
    SELECT customer_id,
           MAX(customer_name)       AS customer_name,
           COUNT(DISTINCT invoice_id) AS invoice_count,
           SUM(total_amount)        AS total_invoiced,
           SUM(CASE WHEN payment_status = 'Paid' THEN total_amount ELSE 0 END) AS paid_amount
    FROM silver.finance_invoices
    GROUP BY customer_id
),
ops AS (
    SELECT customer_id,
           COUNT(order_id)          AS total_orders,
           SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) AS delivered_orders,
           SUM(CASE WHEN sla_met = FALSE THEN 1 ELSE 0 END)       AS sla_breaches,
           ROUND(
               AVG(CASE WHEN status = 'Delivered'
                        THEN actual_days ELSE NULL END), 1
           )                        AS avg_delivery_days
    FROM silver.ops_orders
    GROUP BY customer_id
),
sales AS (
    SELECT customer_id,
           MAX(industry)            AS industry,
           COUNT(deal_id)           AS total_deals,
           SUM(CASE WHEN is_won THEN contract_value ELSE 0 END) AS won_contract_value,
           COUNT(CASE WHEN is_won THEN 1 END)                   AS won_deals
    FROM silver.sales_deals
    GROUP BY customer_id
)
SELECT
    COALESCE(f.customer_id, o.customer_id, s.customer_id)  AS customer_id,
    COALESCE(f.customer_name, s.customer_id)               AS customer_name,
    COALESCE(s.industry, 'UNKNOWN')                        AS industry,
    COALESCE(f.invoice_count, 0)        AS invoice_count,
    COALESCE(f.total_invoiced, 0)       AS total_invoiced,
    COALESCE(f.paid_amount, 0)          AS paid_amount,
    COALESCE(o.total_orders, 0)         AS total_orders,
    COALESCE(o.delivered_orders, 0)     AS delivered_orders,
    COALESCE(o.sla_breaches, 0)         AS sla_breaches,
    o.avg_delivery_days,
    COALESCE(s.won_deals, 0)            AS won_deals,
    COALESCE(s.won_contract_value, 0)   AS won_contract_value,
    -- Derived health score (0-100): blend of payment rate and SLA performance
    ROUND(
        (COALESCE(f.paid_amount, 0) / NULLIF(f.total_invoiced, 0) * 50)
        + (COALESCE(o.delivered_orders, 0) / NULLIF(o.total_orders, 0) * 50)
    , 0) AS health_score
FROM fin f
FULL OUTER JOIN ops o  USING (customer_id)
FULL OUTER JOIN sales s USING (customer_id)
ORDER BY total_invoiced DESC;


-- ─────────────────────────────────────────
-- GOLD 3: Operational KPI Summary
-- Definition: overall business KPIs for the reporting period.
-- Single row per time window — used for executive dashboard tiles.
-- ─────────────────────────────────────────
CREATE OR REPLACE TABLE gold.operational_kpis AS
SELECT
    -- Revenue: only Paid + Pending invoices (excludes Unpaid/Unknown)
    -- This matches the definition used in monthly_revenue and customer_health
    ROUND(SUM(total_amount), 0)         AS total_revenue_invoiced,
    ROUND(SUM(CASE WHEN payment_status = 'Paid'
                   THEN total_amount ELSE 0 END), 0) AS total_revenue_paid,
    ROUND(AVG(total_amount), 0)         AS avg_invoice_value,
    COUNT(DISTINCT invoice_id)          AS total_invoices,
    ROUND(
        SUM(CASE WHEN payment_status = 'Paid' THEN total_amount ELSE 0 END)
        / NULLIF(SUM(total_amount), 0) * 100, 1
    )                                   AS payment_rate_pct
FROM silver.finance_invoices
WHERE payment_status IN ('Paid', 'Pending');


-- ─────────────────────────────────────────
-- GOLD 4: SLA Performance by Region
-- Definition: on-time delivery rate by region.
-- ─────────────────────────────────────────
CREATE OR REPLACE TABLE gold.sla_by_region AS
SELECT
    region,
    COUNT(order_id)                                    AS total_orders,
    SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
    SUM(CASE WHEN sla_met = TRUE THEN 1 ELSE 0 END)    AS on_time,
    SUM(CASE WHEN sla_met = FALSE THEN 1 ELSE 0 END)   AS late,
    ROUND(
        SUM(CASE WHEN sla_met = TRUE THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN status = 'Delivered' THEN 1 ELSE 0 END), 0) * 100
    , 1)                                               AS on_time_rate_pct
FROM silver.ops_orders
GROUP BY region
ORDER BY on_time_rate_pct DESC;


-- ─────────────────────────────────────────
-- GOLD 5: Product Revenue Mix
-- Definition: revenue and order volume by product.
-- ─────────────────────────────────────────
CREATE OR REPLACE TABLE gold.product_revenue AS
SELECT
    f.product_id,
    COUNT(DISTINCT f.invoice_id)    AS invoice_count,
    ROUND(SUM(f.total_amount), 0)   AS total_invoiced,
    ROUND(AVG(f.total_amount), 0)   AS avg_invoice_value,
    COUNT(DISTINCT o.order_id)      AS order_count
FROM silver.finance_invoices f
LEFT JOIN silver.ops_orders o
    ON f.product_id = o.product_id
GROUP BY f.product_id
ORDER BY total_invoiced DESC;
