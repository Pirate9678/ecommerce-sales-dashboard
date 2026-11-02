-- =====================================================================
-- E-Commerce Sales Performance Dashboard — ETL (PostgreSQL)
-- raw_orders (dirty TEXT staging) -> dim_customers / dim_products / fact_sales
--
-- Cleaning rules (mirrored 1:1 in data/clean_data.py so the committed
-- data/final/ecommerce_sales_clean.csv matches this pipeline exactly):
--   1. drop exact duplicate rows (keep first)
--   2. trim whitespace, normalise case (INITCAP)
--   3. order_date must be a real YYYY-MM-DD calendar date, else row dropped
--   4. quantity / unit_price must be numeric and > 0, else row dropped
--   5. discount_pct: blank -> 0, clipped to [0, 80]
--   6. region must be one of North/South/East/West/Central (after normalising)
--   7. customer_id must be present
--   8. derived: net_revenue, order_month (first of month)
--
-- Idempotent: TRUNCATEs the target tables first (safe to re-run).
-- ~5-8% of raw rows are expected to be rejected; the SELECT at the end
-- reports the rejection rate for the data-quality KPI.
-- =====================================================================

TRUNCATE fact_sales, dim_products, dim_customers RESTART IDENTITY;

-- ------------------------------------------------------------------ step 1
-- Dedupe + cast + standardise into a temp staging table.
-- * SELECT DISTINCT removes exact duplicate rows (cheaper here than
--   ROW_NUMBER(); the whole row is the dedupe key).
-- * Regex guards run BEFORE any cast so one malformed value cannot abort
--   the whole load (TO_DATE / ::NUMERIC raise on bad input otherwise).
-- * The date regex enforces real month/day ranges; TO_DATE then only sees
--   plausible strings. (Residual edge: e.g. 2023-02-31 would still raise;
--   the source generator never emits those.)
CREATE TEMP TABLE stg_clean AS
SELECT DISTINCT
    NULLIF(TRIM(order_id), '')                                        AS order_id,
    CASE WHEN TRIM(order_date) ~ '^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$'
         THEN TO_DATE(TRIM(order_date), 'YYYY-MM-DD')
    END                                                              AS order_date,
    INITCAP(TRIM(region))                                             AS region,
    TRIM(state)                                                       AS state,
    TRIM(city)                                                        AS city,
    INITCAP(TRIM(product_category))                                   AS product_category,
    TRIM(product_name)                                                AS product_name,
    CASE WHEN TRIM(quantity) ~ '^[0-9]+(\.[0-9]+)?$'
         THEN TRIM(quantity)::NUMERIC
    END                                                              AS quantity,
    CASE WHEN TRIM(unit_price) ~ '^[0-9]+(\.[0-9]+)?$'
         THEN TRIM(unit_price)::NUMERIC
    END                                                              AS unit_price,
    LEAST(GREATEST(
        COALESCE(
            CASE WHEN TRIM(discount_pct) ~ '^[0-9]+(\.[0-9]+)?$'
                 THEN TRIM(discount_pct)::NUMERIC
            END, 0), 0), 80)                                         AS discount_pct,
    NULLIF(TRIM(customer_id), '')                                     AS customer_id,
    TRIM(customer_age_group)                                          AS age_group,
    INITCAP(TRIM(customer_gender))                                    AS gender,
    TRIM(payment_method)                                              AS payment_method,
    INITCAP(TRIM(order_status))                                       AS order_status
FROM raw_orders;

-- ------------------------------------------------------------------ step 2
-- Apply the validity rules and compute derived columns.
-- Filtering here (not in the fact INSERT) keeps the INSERT a plain,
-- optimisable join with no WHERE-clause surprises.
CREATE TEMP TABLE stg_valid AS
SELECT
    order_id,
    order_date,
    DATE_TRUNC('month', order_date)::DATE                             AS order_month,
    region, state, city,
    product_category, product_name,
    quantity, unit_price, discount_pct,
    ROUND(quantity * unit_price * (1 - discount_pct / 100), 2)        AS net_revenue,
    customer_id, age_group, gender, payment_method, order_status
FROM stg_clean
WHERE order_id    IS NOT NULL
  AND order_date  IS NOT NULL
  AND quantity    IS NOT NULL AND quantity   > 0
  AND unit_price  IS NOT NULL AND unit_price > 0
  AND region IN ('North', 'South', 'East', 'West', 'Central')
  AND customer_id IS NOT NULL;

-- ------------------------------------------------------------------ step 3
-- Dimensions first (surrogate keys), then the fact.
-- DISTINCT keeps dimension builds set-based: one pass, no row-by-row logic.
INSERT INTO dim_customers (customer_id, age_group, gender)
SELECT DISTINCT customer_id, age_group, gender
FROM stg_valid;

INSERT INTO dim_products (product_name, product_category)
SELECT DISTINCT product_name, product_category
FROM stg_valid;

-- The joins below are on the dimension UNIQUE keys, so the planner uses
-- nested-loop / hash joins on indexed lookups instead of scanning.
INSERT INTO fact_sales (
    order_id, order_date, order_month,
    customer_key, product_key,
    region, state, city,
    quantity, unit_price, discount_pct, net_revenue,
    payment_method, order_status
)
SELECT
    v.order_id, v.order_date, v.order_month,
    c.customer_key, p.product_key,
    v.region, v.state, v.city,
    v.quantity::INTEGER,
    v.unit_price::NUMERIC(12, 2),
    v.discount_pct::NUMERIC(5, 2),
    v.net_revenue,
    v.payment_method, v.order_status
FROM stg_valid v
JOIN dim_customers c
  ON c.customer_id = v.customer_id
JOIN dim_products p
  ON p.product_name = v.product_name
 AND p.product_category = v.product_category;

-- ------------------------------------------------------------------ data-quality report
-- Rejection rate for the weekly data-quality KPI (~5-8% expected).
SELECT
    (SELECT COUNT(*) FROM raw_orders)                      AS raw_rows,
    (SELECT COUNT(*) FROM fact_sales)                      AS clean_rows,
    ROUND(100.0 * ((SELECT COUNT(*) FROM raw_orders)
                 - (SELECT COUNT(*) FROM fact_sales))
                 / (SELECT COUNT(*) FROM raw_orders), 2)   AS rejected_pct;
