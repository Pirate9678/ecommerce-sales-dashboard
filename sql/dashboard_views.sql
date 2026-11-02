-- =====================================================================
-- E-Commerce Sales Performance Dashboard — dashboard views (PostgreSQL)
-- These 7 views power the 8 Power BI visuals (see powerbi/build_guide.md).
--
-- Convention: every REVENUE metric filters order_status = 'Delivered'.
-- Returned/cancelled orders stay in fact_sales for ops reporting but must
-- not inflate sales KPIs. Each view documents its own optimisation.
-- =====================================================================

-- ------------------------------------------------------------------ 1
-- Monthly revenue by region  ->  line chart "Revenue trend by region"
-- Optimisation: GROUP BY hits idx_fact_order_month / idx_fact_region;
-- the status predicate is applied BEFORE aggregation so cancelled rows
-- are excluded by the idx_fact_status bitmap scan instead of after.
CREATE OR REPLACE VIEW vw_monthly_revenue_by_region AS
SELECT
    order_month,
    region,
    SUM(net_revenue)                AS revenue,
    COUNT(*)                        AS orders,
    ROUND(AVG(net_revenue), 2)      AS avg_order_value
FROM fact_sales
WHERE order_status = 'Delivered'
GROUP BY order_month, region;

-- ------------------------------------------------------------------ 2
-- Top products by revenue  ->  bar chart "Top 10 products"
-- Optimisation: aggregates on the narrow (product_key) join key via
-- idx_fact_product, then LIMIT 20 keeps the visual's working set tiny.
-- Power BI takes TOPN(10) client-side from these 20.
CREATE OR REPLACE VIEW vw_top_products AS
SELECT
    p.product_name,
    p.product_category,
    SUM(f.net_revenue)              AS revenue,
    SUM(f.quantity)                 AS units_sold,
    COUNT(*)                        AS orders
FROM fact_sales f
JOIN dim_products p ON p.product_key = f.product_key
WHERE f.order_status = 'Delivered'
GROUP BY p.product_name, p.product_category
ORDER BY revenue DESC
LIMIT 20;

-- ------------------------------------------------------------------ 3
-- Customer demographics  ->  stacked bar "Revenue by age group x gender"
-- Optimisation: single pass over fact_sales; COUNT(DISTINCT customer_key)
-- uses a hash aggregate -- fine at this scale, and far cheaper than a
-- self-join per demographic slice.
CREATE OR REPLACE VIEW vw_customer_demographics AS
SELECT
    c.age_group,
    c.gender,
    COUNT(DISTINCT f.customer_key)  AS customers,
    COUNT(*)                        AS orders,
    SUM(f.net_revenue)              AS revenue,
    ROUND(AVG(f.net_revenue), 2)    AS avg_order_value
FROM fact_sales f
JOIN dim_customers c ON c.customer_key = f.customer_key
WHERE f.order_status = 'Delivered'
GROUP BY c.age_group, c.gender;

-- ------------------------------------------------------------------ 4
-- Year-over-year growth  ->  KPI card "YoY growth %" + trend line
-- Optimisation: the CTE pre-aggregates to 33 monthly rows FIRST, so the
-- LAG(..., 12) window scans 33 rows, not 55k. Never window over the fact.
CREATE OR REPLACE VIEW vw_yoy_growth AS
WITH monthly AS (
    SELECT order_month, SUM(net_revenue) AS revenue
    FROM fact_sales
    WHERE order_status = 'Delivered'
    GROUP BY order_month
)
SELECT
    order_month,
    revenue,
    LAG(revenue, 12) OVER (ORDER BY order_month) AS revenue_prior_year,
    ROUND(100.0 * (revenue - LAG(revenue, 12) OVER (ORDER BY order_month))
          / NULLIF(LAG(revenue, 12) OVER (ORDER BY order_month), 0), 2)
                                                AS yoy_growth_pct
FROM monthly;

-- ------------------------------------------------------------------ 5
-- Category share of revenue  ->  donut "Revenue share by category"
-- Optimisation: the grand total is computed once in a scalar subquery
-- (not a cross join), so the aggregation stays a single grouped pass.
CREATE OR REPLACE VIEW vw_category_share AS
SELECT
    p.product_category              AS category,
    SUM(f.net_revenue)              AS revenue,
    ROUND(100.0 * SUM(f.net_revenue)
          / SUM(SUM(f.net_revenue)) OVER (), 2) AS share_pct
FROM fact_sales f
JOIN dim_products p ON p.product_key = f.product_key
WHERE f.order_status = 'Delivered'
GROUP BY p.product_category;

-- ------------------------------------------------------------------ 6
-- Payment-method mix  ->  bar/donut "Orders & revenue by payment method"
-- Optimisation: one grouped scan serves both the order-count and revenue
-- measures; no second pass needed for the two visuals that share it.
CREATE OR REPLACE VIEW vw_payment_method_mix AS
SELECT
    payment_method,
    COUNT(*)                        AS orders,
    SUM(net_revenue)                AS revenue,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS order_share_pct
FROM fact_sales
WHERE order_status = 'Delivered'
GROUP BY payment_method;

-- ------------------------------------------------------------------ 7
-- Discount impact on margin  ->  table/bar "Discount vs margin by category"
-- discount_given is the INR value handed to customers; net_margin_proxy
-- shows what revenue remains after discount per category.
-- Optimisation: all expressions are computed from already-aggregated
-- columns in the same GROUP BY pass -- no correlated subqueries.
CREATE OR REPLACE VIEW vw_discount_impact AS
SELECT
    p.product_category              AS category,
    COUNT(*)                        AS orders,
    ROUND(AVG(f.discount_pct), 2)   AS avg_discount_pct,
    SUM(f.quantity * f.unit_price)  AS gross_revenue,
    SUM(f.quantity * f.unit_price * f.discount_pct / 100) AS discount_given,
    SUM(f.net_revenue)              AS net_revenue,
    ROUND(100.0 * SUM(f.net_revenue)
          / NULLIF(SUM(f.quantity * f.unit_price), 0), 2) AS net_margin_proxy_pct
FROM fact_sales f
JOIN dim_products p ON p.product_key = f.product_key
WHERE f.order_status = 'Delivered'
GROUP BY p.product_category;
