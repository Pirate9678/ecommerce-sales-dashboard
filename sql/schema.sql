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
