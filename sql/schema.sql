-- =====================================================================
-- E-Commerce Sales Performance Dashboard — schema (PostgreSQL 14+)
-- Star schema: raw_orders (staging) -> dim_customers, dim_products, fact_sales
--
-- Load the raw CSV first:
--   COPY raw_orders FROM '/path/to/data/raw/ecommerce_orders.csv'
--   WITH (FORMAT csv, HEADER true);
-- Then run cleaning.sql, which populates the dims and the fact table.
-- =====================================================================

DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_products;
DROP TABLE IF EXISTS dim_customers;
DROP TABLE IF EXISTS raw_orders;

-- ---------------------------------------------------------------- staging
-- Every column is TEXT on purpose: the source file contains dirty rows
-- (blank fields, malformed dates, negative quantities). Loading as TEXT
-- never fails; cleaning.sql casts and validates afterwards.
CREATE TABLE raw_orders (
    order_id           TEXT,
    order_date         TEXT,
    region             TEXT,
    state              TEXT,
    city               TEXT,
    product_category   TEXT,
    product_name       TEXT,
    quantity           TEXT,
    unit_price         TEXT,
    discount_pct       TEXT,
    customer_id        TEXT,
    customer_age_group TEXT,
    customer_gender    TEXT,
    payment_method     TEXT,
    order_status       TEXT
);

-- ---------------------------------------------------------------- dimensions
CREATE TABLE dim_customers (
    customer_key SERIAL PRIMARY KEY,
    customer_id  TEXT NOT NULL UNIQUE,
    age_group    TEXT,
    gender       TEXT
);

CREATE TABLE dim_products (
    product_key      SERIAL PRIMARY KEY,
    product_name     TEXT NOT NULL,
    product_category TEXT NOT NULL,
    UNIQUE (product_name, product_category)
);

-- ---------------------------------------------------------------- fact
CREATE TABLE fact_sales (
    sale_id        SERIAL PRIMARY KEY,
    order_id       TEXT NOT NULL,
    order_date     DATE NOT NULL,
    order_month    DATE NOT NULL,          -- first day of the month (time intelligence)
    customer_key   INTEGER NOT NULL REFERENCES dim_customers (customer_key),
    product_key    INTEGER NOT NULL REFERENCES dim_products (product_key),
    region         TEXT NOT NULL,          -- North | South | East | West | Central
    state          TEXT,
    city           TEXT,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
    discount_pct   NUMERIC(5, 2) NOT NULL DEFAULT 0
                   CHECK (discount_pct BETWEEN 0 AND 80),
    net_revenue    NUMERIC(14, 2) NOT NULL, -- quantity * unit_price * (1 - discount_pct/100)
    payment_method TEXT,
    order_status   TEXT NOT NULL           -- Delivered | Cancelled | Returned
);

-- ---------------------------------------------------------------- indexes
-- Each index matches a dashboard access pattern (slicers / GROUP BYs in
-- dashboard_views.sql). Without them every visual would seq-scan ~55k rows;
-- with them the planner uses index-only / bitmap scans on the hot columns.
CREATE INDEX idx_fact_order_date  ON fact_sales (order_date);    -- trend & YoY visuals
CREATE INDEX idx_fact_order_month ON fact_sales (order_month);   -- monthly rollups
CREATE INDEX idx_fact_region      ON fact_sales (region);        -- regional slicer
CREATE INDEX idx_fact_product     ON fact_sales (product_key);   -- product performance
CREATE INDEX idx_fact_customer    ON fact_sales (customer_key);  -- demographics
CREATE INDEX idx_fact_status      ON fact_sales (order_status);  -- delivered-only revenue filter

-- ---------------------------------------------------------------- composite
-- Added Nov 2026 (scaling work): every dashboard view filters
-- order_status = 'Delivered' FIRST and then groups by one more column, so
-- the composite indexes below start with order_status and carry the
-- measure columns (net_revenue, quantity, discount_pct) as trailing key
-- columns, making each index COVERING for its views — the planner reads
-- the index only, never the table. (PostgreSQL users can equivalently
-- write these with INCLUDE (net_revenue, ...) instead of trailing keys;
-- this SQLite mirror's engine rejects INCLUDE, so the trailing-key form
-- is used in both files to keep them identical and testable.)
--
-- Measured in benchmark/benchmark.py (SQLite mirror, median of 3 runs,
-- 1M rows, 4-vCPU host, 8 Nov 2026) — covering vs single-column indexes:
--   monthly revenue by region  1.19s -> 0.21s  (5.7x)
--   top products               1.19s -> 0.75s  (1.6x)
--   customer demographics      1.66s -> 0.90s  (1.8x)
--   YoY growth                 0.71s -> 0.14s  (5.0x)
--   category share             0.77s -> 0.45s  (1.7x)
--   payment-method mix         0.67s -> 0.14s  (4.9x)
--   discount impact            1.10s -> 1.09s  (1.0x — it groups by the
--     dimension's product_category, so index order can't serve the GROUP
--     BY; the index still speeds the product join)
--   all 7 views total          7.28s -> 3.68s  (2.0x)
-- Honest caveat: the FIRST version of these indexes was non-covering
-- (no payload columns) and measured SLOWER than single-column indexes at
-- 1M rows in the same mirror — a composite index only pays when it
-- covers the query. The numbers above are for the covering form.
CREATE INDEX idx_fact_status_month_region
    ON fact_sales (order_status, order_month, region, net_revenue);
                                                            -- vw_monthly_revenue_by_region, vw_yoy_growth
CREATE INDEX idx_fact_status_product
    ON fact_sales (order_status, product_key, net_revenue, quantity, discount_pct);
                                                            -- vw_top_products, vw_category_share, vw_discount_impact
CREATE INDEX idx_fact_status_customer
    ON fact_sales (order_status, customer_key, net_revenue);
                                                            -- vw_customer_demographics
CREATE INDEX idx_fact_status_payment
    ON fact_sales (order_status, payment_method, net_revenue);
                                                            -- vw_payment_method_mix

-- After a bulk load, refresh planner statistics so the new indexes are used:
--   ANALYZE fact_sales;
