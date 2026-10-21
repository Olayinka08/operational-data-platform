-- silver_finance.sql
-- Cleans and standardises the finance bronze table.
-- Problems solved:
--   1. Date format DD/MM/YYYY converted to ISO YYYY-MM-DD
--   2. Customer ID FIN-CXXX stripped to canonical CXXX
--   3. Duplicate invoice_ids resolved (keep highest amount — billing error pattern)
--   4. Missing customer_name flagged as 'UNKNOWN' rather than blank
--   5. payment_status normalised to consistent values

CREATE OR REPLACE TABLE silver.finance_invoices AS
WITH deduped AS (
    -- Remove duplicate invoice_ids, keeping the row with the highest total_amount
    -- (finance system bug: duplicate invoices had slightly inflated amounts)
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY invoice_id
               ORDER BY CAST(total_amount AS DOUBLE) DESC
           ) AS rn
    FROM bronze.finance_invoices
),
cleaned AS (
    SELECT
        invoice_id,
        -- Standardise customer_id: strip 'FIN-' prefix to match ops and master
        REPLACE(customer_id, 'FIN-', '') AS customer_id,
        -- Coalesce empty customer_name to 'UNKNOWN'
        CASE WHEN customer_name = '' OR customer_name IS NULL
             THEN 'UNKNOWN' ELSE customer_name END AS customer_name,
        product_id,
        CAST(quantity AS INTEGER) AS quantity,
        CAST(unit_price AS DOUBLE) AS unit_price,
        CAST(total_amount AS DOUBLE) AS total_amount,
        -- Convert DD/MM/YYYY -> ISO date
        STRPTIME(invoice_date, '%d/%m/%Y')::DATE AS invoice_date,
        -- Normalise payment_status
        CASE payment_status
            WHEN 'Yes'     THEN 'Paid'
            WHEN 'No'      THEN 'Unpaid'
            WHEN 'Pending' THEN 'Pending'
            ELSE 'Unknown'
        END AS payment_status,
        region
    FROM deduped
    WHERE rn = 1
)
SELECT * FROM cleaned;
