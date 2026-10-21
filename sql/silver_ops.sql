-- silver_ops.sql
-- Cleans and standardises the ops bronze table.
-- Problems solved:
--   1. Dates already ISO — cast to DATE type
--   2. Null delivery_date / sla_met handled (in-transit orders)
--   3. status values normalised
--   4. Derived column: days_overdue for SLA breach analysis

CREATE OR REPLACE TABLE silver.ops_orders AS
SELECT
    order_id,
    customer_id,    -- already clean CXXX format
    product_id,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(order_date AS DATE) AS order_date,
    -- Null delivery_date means order not yet delivered
    CASE WHEN delivery_date = '' OR delivery_date IS NULL
         THEN NULL
         ELSE CAST(delivery_date AS DATE)
    END AS delivery_date,
    CAST(sla_days AS INTEGER) AS sla_days,
    CAST(actual_days AS INTEGER) AS actual_days,
    -- Normalise sla_met: null for open orders
    CASE WHEN sla_met = '' OR sla_met IS NULL THEN NULL
         WHEN sla_met = 'Yes' THEN TRUE
         ELSE FALSE
    END AS sla_met,
    -- Normalise status: if delivery_date is null, cannot be Delivered
    CASE
        WHEN (delivery_date = '' OR delivery_date IS NULL) AND status = 'Delivered'
             THEN 'In Transit'
        WHEN status = 'Delivered'   THEN 'Delivered'
        WHEN status = 'In Transit'  THEN 'In Transit'
        WHEN status = 'Cancelled'   THEN 'Cancelled'
        ELSE 'Unknown'
    END AS status,
    region,
    -- Derived: how many days over SLA (positive = breach, null = open/cancelled)
    CASE WHEN delivery_date IS NOT NULL AND delivery_date != ''
         THEN CAST(actual_days AS INTEGER) - CAST(sla_days AS INTEGER)
         ELSE NULL
    END AS days_vs_sla
FROM bronze.ops_orders;
