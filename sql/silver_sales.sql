-- silver_sales.sql
-- Cleans and standardises the sales bronze table.
-- Problems solved:
--   1. Date format MM-DD-YYYY converted to ISO YYYY-MM-DD
--   2. Customer ID SALES-CXXX stripped to canonical CXXX
--   3. Missing industry flagged as 'UNKNOWN'
--   4. Only 'Closed Won' deals carried forward to gold revenue metrics

CREATE OR REPLACE TABLE silver.sales_deals AS
SELECT
    deal_id,
    -- Standardise customer_id: strip 'SALES-' prefix
    REPLACE(customer_id, 'SALES-', '') AS customer_id,
    CASE WHEN customer_name = '' OR customer_name IS NULL
         THEN 'UNKNOWN' ELSE customer_name END AS customer_name,
    product_id,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(contract_value AS DOUBLE) AS contract_value,
    -- Convert MM-DD-YYYY -> ISO date
    STRPTIME(close_date, '%m-%d-%Y')::DATE AS close_date,
    deal_stage,
    sales_owner,
    CASE WHEN industry = '' OR industry IS NULL
         THEN 'UNKNOWN' ELSE industry END AS industry,
    region,
    -- Flag for gold layer filtering
    CASE WHEN deal_stage = 'Closed Won' THEN TRUE ELSE FALSE END AS is_won
FROM bronze.sales_deals;
