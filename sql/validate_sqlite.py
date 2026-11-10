#!/usr/bin/env python3
"""
Validate the SQL layer without a Postgres server.

The committed files (sql/schema.sql, sql/cleaning.sql, sql/dashboard_views.sql)
are written in PostgreSQL dialect. This script executes a SQLite ADAPTATION of
the exact same logic -- same cleaning rules, same star schema, same 7 views --
against the real CSVs, and cross-checks the outcome against
data/final/ecommerce_sales_clean.csv (produced by data/clean_data.py, which
mirrors sql/cleaning.sql rule-for-rule).

Run from the repo root:  python3 sql/validate_sqlite.py

What it proves:
  * every cleaning rule and every dashboard view runs without SQL errors
  * the SQL pipeline and the Python pipeline converge on the same result
    (identical row counts and revenue totals)

Adaptation notes (SQLite vs PostgreSQL):
  * `/ 100.0` instead of `/ 100` — SQLite does integer division on two
    integers; PostgreSQL's NUMERIC division is unaffected, so the committed
    .sql files keep `/ 100`.
  * `valid_date()` / `regexp()` / `initcap()` are Python functions registered
    into SQLite, standing in for TO_DATE + regex guards and INITCAP.
"""
import csv
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "ecommerce_orders.csv"
CLEAN_CSV = ROOT / "data" / "final" / "ecommerce_sales_clean.csv"

FAILURES = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILURES.append(name)


def valid_date(s):
    r"""Mirror of: regex ^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$ + TO_DATE."""
    if not s or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])", s):
        return 0
    try:
        date(*map(int, s.split("-")))
        return 1
    except ValueError:
        return 0


def regexp(pattern, value):
    return 1 if value is not None and re.search(pattern, value) else 0


def initcap(s):
    return s.strip().title() if s else s


def build_db(raw_csv=RAW_CSV, clean_csv=CLEAN_CSV, composite_indexes=True):
    """Build the in-memory SQLite DB: schema + raw load + ETL + views.
    SQLite adaptation of sql/schema.sql, sql/cleaning.sql and
    sql/dashboard_views.sql (same rules, same logic). Returns (con, cur).

    composite_indexes=False builds the pre-Nov-2026 index set (single-column
    only) so benchmark/benchmark.py can measure what the composite indexes
    are worth at each scale.
    """
    con = sqlite3.connect(":memory:")
    con.create_function("regexp", 2, regexp)
    con.create_function("valid_date", 1, valid_date)
    con.create_function("initcap", 1, initcap)
    cur = con.cursor()

    # ---- schema (SQLite adaptation of sql/schema.sql) ---------------------
    idx_extra = """
        -- Covering composite indexes (Nov 2026, mirrors sql/schema.sql):
        -- every view filters order_status='Delivered' first, then groups by
        -- one more column; the trailing key columns carry the measures so
        -- the planner reads the index only. Measured in benchmark/benchmark.py.
        CREATE INDEX idx_fact_status_month_region
            ON fact_sales (order_status, order_month, region, net_revenue);
        CREATE INDEX idx_fact_status_product
            ON fact_sales (order_status, product_key, net_revenue, quantity, discount_pct);
        CREATE INDEX idx_fact_status_customer
            ON fact_sales (order_status, customer_key, net_revenue);
        CREATE INDEX idx_fact_status_payment
            ON fact_sales (order_status, payment_method, net_revenue);
    """ if composite_indexes else ""
    cur.executescript(f"""
        CREATE TABLE raw_orders (
            order_id TEXT, order_date TEXT, region TEXT, state TEXT, city TEXT,
            product_category TEXT, product_name TEXT, quantity TEXT,
            unit_price TEXT, discount_pct TEXT, customer_id TEXT,
            customer_age_group TEXT, customer_gender TEXT,
            payment_method TEXT, order_status TEXT);
        CREATE TABLE dim_customers (
            customer_key INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL UNIQUE, age_group TEXT, gender TEXT);
        CREATE TABLE dim_products (
            product_key INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL, product_category TEXT NOT NULL,
            UNIQUE (product_name, product_category));
        CREATE TABLE fact_sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL, order_date DATE NOT NULL, order_month DATE NOT NULL,
            customer_key INTEGER NOT NULL REFERENCES dim_customers(customer_key),
            product_key INTEGER NOT NULL REFERENCES dim_products(product_key),
            region TEXT NOT NULL, state TEXT, city TEXT,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price REAL NOT NULL CHECK (unit_price > 0),
            discount_pct REAL NOT NULL DEFAULT 0 CHECK (discount_pct BETWEEN 0 AND 80),
            net_revenue REAL NOT NULL,
            payment_method TEXT, order_status TEXT NOT NULL);
        CREATE INDEX idx_fact_order_month ON fact_sales (order_month);
        CREATE INDEX idx_fact_region      ON fact_sales (region);
        CREATE INDEX idx_fact_status      ON fact_sales (order_status);
        {idx_extra}
    """)

    # ---- load raw CSV ------------------------------------------------------
    with open(raw_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cur.executemany(
        "INSERT INTO raw_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [[r.get(c) for c in ("order_id", "order_date", "region", "state", "city",
                             "product_category", "product_name", "quantity",
                             "unit_price", "discount_pct", "customer_id",
                             "customer_age_group", "customer_gender",
                             "payment_method", "order_status")] for r in rows])
    con.commit()
    check("raw rows loaded", cur.execute("SELECT COUNT(*) FROM raw_orders").fetchone()[0] == len(rows),
          f"({len(rows):,} rows)")

    # ---- ETL (SQLite adaptation of sql/cleaning.sql) -----------------------
    cur.executescript("""
        CREATE TEMP TABLE stg_clean AS
        SELECT DISTINCT
            NULLIF(TRIM(order_id), '') AS order_id,
            CASE WHEN valid_date(TRIM(order_date)) = 1 THEN TRIM(order_date) END AS order_date,
            initcap(TRIM(region))        AS region,
            TRIM(state)                  AS state,
            TRIM(city)                   AS city,
            initcap(TRIM(product_category)) AS product_category,
            TRIM(product_name)           AS product_name,
            CASE WHEN TRIM(quantity)   REGEXP '^[0-9]+(\\.[0-9]+)?$'
                 THEN CAST(TRIM(quantity) AS REAL) END AS quantity,
            CASE WHEN TRIM(unit_price) REGEXP '^[0-9]+(\\.[0-9]+)?$'
                 THEN CAST(TRIM(unit_price) AS REAL) END AS unit_price,
            min(max(COALESCE(
                CASE WHEN TRIM(discount_pct) REGEXP '^[0-9]+(\\.[0-9]+)?$'
                     THEN CAST(TRIM(discount_pct) AS REAL) END, 0), 0), 80)
                                             AS discount_pct,
            NULLIF(TRIM(customer_id), '') AS customer_id,
            TRIM(customer_age_group)     AS age_group,
            initcap(TRIM(customer_gender)) AS gender,
            TRIM(payment_method)         AS payment_method,
            initcap(TRIM(order_status))  AS order_status
        FROM raw_orders;

        CREATE TEMP TABLE stg_valid AS
        SELECT order_id, order_date,
               date(order_date, 'start of month') AS order_month,
               region, state, city, product_category, product_name,
               quantity, unit_price, discount_pct,
               ROUND(quantity * unit_price * (1 - discount_pct / 100.0), 2) AS net_revenue, -- /100.0: SQLite integer division guard (PG uses NUMERIC, unaffected)
               customer_id, age_group, gender, payment_method, order_status
        FROM stg_clean
        WHERE order_id IS NOT NULL
          AND order_date IS NOT NULL
          AND quantity IS NOT NULL AND quantity > 0
          AND unit_price IS NOT NULL AND unit_price > 0
          AND region IN ('North','South','East','West','Central')
          AND customer_id IS NOT NULL;

        INSERT INTO dim_customers (customer_id, age_group, gender)
        SELECT DISTINCT customer_id, age_group, gender FROM stg_valid;

        INSERT INTO dim_products (product_name, product_category)
        SELECT DISTINCT product_name, product_category FROM stg_valid;

        INSERT INTO fact_sales
            (order_id, order_date, order_month, customer_key, product_key,
             region, state, city, quantity, unit_price, discount_pct,
             net_revenue, payment_method, order_status)
        SELECT v.order_id, v.order_date, v.order_month,
               c.customer_key, p.product_key,
               v.region, v.state, v.city,
               CAST(v.quantity AS INTEGER), v.unit_price, v.discount_pct,
               v.net_revenue, v.payment_method, v.order_status
        FROM stg_valid v
        JOIN dim_customers c ON c.customer_id = v.customer_id
        JOIN dim_products p  ON p.product_name = v.product_name
                            AND p.product_category = v.product_category;
    """)
    con.commit()

    # ---- dashboard views (SQLite adaptation of sql/dashboard_views.sql) ----
    cur.executescript("""
        CREATE VIEW vw_monthly_revenue_by_region AS
        SELECT order_month, region, SUM(net_revenue) AS revenue,
               COUNT(*) AS orders, ROUND(AVG(net_revenue), 2) AS avg_order_value
        FROM fact_sales WHERE order_status = 'Delivered'
        GROUP BY order_month, region;

        CREATE VIEW vw_top_products AS
        SELECT p.product_name, p.product_category,
               SUM(f.net_revenue) AS revenue, SUM(f.quantity) AS units_sold,
               COUNT(*) AS orders
        FROM fact_sales f JOIN dim_products p ON p.product_key = f.product_key
        WHERE f.order_status = 'Delivered'
        GROUP BY p.product_name, p.product_category
        ORDER BY revenue DESC LIMIT 20;

        CREATE VIEW vw_customer_demographics AS
        SELECT c.age_group, c.gender,
               COUNT(DISTINCT f.customer_key) AS customers,
               COUNT(*) AS orders, SUM(f.net_revenue) AS revenue,
               ROUND(AVG(f.net_revenue), 2) AS avg_order_value
        FROM fact_sales f JOIN dim_customers c ON c.customer_key = f.customer_key
        WHERE f.order_status = 'Delivered'
        GROUP BY c.age_group, c.gender;

        CREATE VIEW vw_yoy_growth AS
        WITH monthly AS (
            SELECT order_month, SUM(net_revenue) AS revenue
            FROM fact_sales WHERE order_status = 'Delivered' GROUP BY order_month)
        SELECT order_month, revenue,
               LAG(revenue, 12) OVER (ORDER BY order_month) AS revenue_prior_year,
               ROUND(100.0 * (revenue - LAG(revenue, 12) OVER (ORDER BY order_month))
                     / NULLIF(LAG(revenue, 12) OVER (ORDER BY order_month), 0), 2)
               AS yoy_growth_pct
        FROM monthly;

        CREATE VIEW vw_category_share AS
        SELECT p.product_category AS category, SUM(f.net_revenue) AS revenue,
               ROUND(100.0 * SUM(f.net_revenue)
                     / SUM(SUM(f.net_revenue)) OVER (), 2) AS share_pct
        FROM fact_sales f JOIN dim_products p ON p.product_key = f.product_key
        WHERE f.order_status = 'Delivered'
        GROUP BY p.product_category;

        CREATE VIEW vw_payment_method_mix AS
        SELECT payment_method, COUNT(*) AS orders, SUM(net_revenue) AS revenue,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS order_share_pct
        FROM fact_sales WHERE order_status = 'Delivered'
        GROUP BY payment_method;

        CREATE VIEW vw_discount_impact AS
        SELECT p.product_category AS category, COUNT(*) AS orders,
               ROUND(AVG(f.discount_pct), 2) AS avg_discount_pct,
               SUM(f.quantity * f.unit_price) AS gross_revenue,
               SUM(f.quantity * f.unit_price * f.discount_pct / 100.0) AS discount_given,
               SUM(f.net_revenue) AS net_revenue,
               ROUND(100.0 * SUM(f.net_revenue)
                     / NULLIF(SUM(f.quantity * f.unit_price), 0), 2) AS net_margin_proxy_pct
        FROM fact_sales f JOIN dim_products p ON p.product_key = f.product_key
        WHERE f.order_status = 'Delivered'
        GROUP BY p.product_category;
    """)

    # ---- cross-checks against the pandas-cleaned CSV -----------------------
    return con, cur


def run_checks(con, clean_csv=CLEAN_CSV):
    """Validate the built DB against data/final/ecommerce_sales_clean.csv."""
    import pandas as pd
    clean = pd.read_csv(clean_csv)
    cur = con.cursor()
    n_fact = cur.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    check("fact row count == cleaned CSV row count", n_fact == len(clean),
          f"(sql={n_fact:,} csv={len(clean):,})")

    rev_sql = cur.execute(
        "SELECT SUM(net_revenue) FROM fact_sales WHERE order_status='Delivered'").fetchone()[0]
    rev_csv = float(clean.loc[clean.order_status == "Delivered", "net_revenue"].sum())
    # Tolerance: SQLite ROUND() breaks half-cent ties away from zero while
    # numpy/pandas use banker's rounding, so per-row values can differ by
    # at most ₹0.01. ₹1,000 on a ~₹638M total (0.00016%) proves the logic
    # converges; anything bigger would signal a real formula divergence.
    check("delivered revenue matches CSV", abs(rev_sql - rev_csv) < 1000,
          f"(sql=₹{rev_sql:,.0f} csv=₹{rev_csv:,.0f} diff=₹{abs(rev_sql - rev_csv):,.2f})")

    regions_sql = sorted(r[0] for r in cur.execute("SELECT DISTINCT region FROM fact_sales"))
    check("regions match CSV", regions_sql == sorted(clean.region.unique()), str(regions_sql))

    top_sql = cur.execute("SELECT product_name, revenue FROM vw_top_products LIMIT 1").fetchone()
    top_csv = clean[clean.order_status == "Delivered"].groupby("product_name")["net_revenue"].sum().idxmax()
    check("top product agrees with CSV", top_sql[0] == top_csv, f"({top_sql[0]})")

    views = {"vw_monthly_revenue_by_region": 150, "vw_top_products": 20,
             "vw_customer_demographics": 8, "vw_yoy_growth": 33,
             "vw_category_share": 5, "vw_payment_method_mix": 6,
             "vw_discount_impact": 5}
    for v, minimum in views.items():
        n = cur.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
        check(f"view {v} returns rows", n >= minimum, f"({n} rows)")

    yoy = cur.execute(
        "SELECT yoy_growth_pct FROM vw_yoy_growth WHERE order_month='2024-10-01'").fetchone()
    check("YoY sample computable", yoy is not None and yoy[0] is not None,
          f"(2024-10 YoY={yoy[0] if yoy else 'n/a'}%)")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED: {FAILURES}")
        sys.exit(1)
    print("ALL CHECKS PASSED — SQL logic is proven runnable and consistent "
          "with data/clean_data.py output.")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Validate the SQL layer.")
    ap.add_argument("--raw", type=Path, default=RAW_CSV)
    ap.add_argument("--clean", type=Path, default=CLEAN_CSV)
    ap.add_argument("--no-composite-indexes", action="store_true",
                    help="build the pre-Nov-2026 index set (benchmark use)")
    args = ap.parse_args()
    con, _ = build_db(raw_csv=args.raw, clean_csv=args.clean,
                      composite_indexes=not args.no_composite_indexes)
    run_checks(con, clean_csv=args.clean)


if __name__ == "__main__":
    main()
