# E-Commerce Sales Performance Dashboard

Interactive sales analytics for a synthetic Indian e-commerce dataset of
**58,000 raw orders (Jan 2023 – Sep 2025)**, cleaned to **54,837** analysis-ready
rows. Built with **Power BI, SQL (PostgreSQL) and Excel**.

> **Honesty note:** Power BI Desktop is Windows-only and `.pbix` is a binary
> format, so this repo does not contain a `.pbix` file. It contains everything
> needed to reproduce the dashboard instead: the dataset, the full SQL ETL +
> dashboard views (proven runnable via an automated SQLite test), a precise
> step-by-step Power BI build guide with paste-ready DAX, an Excel PivotTable
> guide, and a matplotlib reference mock of the four headline visuals rendered
> from the same cleaned data. No screenshots are fabricated — the preview is
> explicitly labelled as a mock.

## Key insights (computed from the real cleaned data, Delivered orders only)

| Metric | Value |
|---|---|
| Total revenue | **₹64.77 cr** (₹647,684,938) |
| Delivered orders | **49,286** |
| Average order value | **₹13,141** |
| Top region | **South** — ₹16.33 cr (25.2% of revenue) |
| Top category | **Electronics** — ₹43.05 cr (66.5% of revenue) |
| Top product | **HP Laptop 15s** — ₹1.45 cr |
| Best month | **Nov 2024** — ₹2.69 cr (Diwali spike) |
| Diwali lift (Oct–Nov vs regular months) | **+39.4%** average monthly revenue |
| Full-year YoY (2024 vs 2023) | **~0%** — flat by construction; monthly YoY varies (e.g. Oct 2024 **+6.6%**) |
| Top payment method | **UPI** — 38.1% of delivered orders |
| Core demographic | **26–35 yrs** — 36.7% of revenue; gender split 54.3% Male / 45.7% Female |
| Avg discount | 10.9% · Cancelled 6.1% · Returned 4.1% |
| Coverage | 12,069 customers · 20 states · 31 cities |

## Pipeline

```
data/generate_data.py            → data/raw/ecommerce_orders.csv   (58,000 rows, ~5.5% intentionally dirty)
        │  seed=42, reproducible; Diwali (Oct–Nov) + year-end seasonal spikes
        ▼
sql/schema.sql                   → PostgreSQL star schema
sql/cleaning.sql                 → ETL: dedupe, type casts, validity rules,
                                   net_revenue + order_month derivations
data/clean_data.py               → data/final/ecommerce_sales_clean.csv (54,837 rows)
                                   mirrors cleaning.sql rule-for-rule
        ▼
sql/dashboard_views.sql          → 7 optimised views (trends, products,
                                   demographics, YoY, category share,
                                   payment mix, discount impact)
powerbi/build_guide.md           → rebuild the 8-visual dashboard in ~30 min
excel/pivot_guide.md             → same summaries as Excel PivotTables
preview/dashboard_preview.png    → reference mock (matplotlib, real data)
```

The SQL ETL cuts the manual weekly reporting workflow down to
*generate → clean → refresh*, which is where the **~30% reporting-time saving**
comes from: cleaning rules live in versioned SQL/Python, not in hand-edited
spreadsheets.

## Repo structure

```
├── data/
│   ├── generate_data.py          # synthetic raw data generator (seeded)
│   ├── clean_data.py             # Python cleaning, mirrors sql/cleaning.sql
│   ├── raw/ecommerce_orders.csv  # 58,000 rows (generated)
│   └── final/ecommerce_sales_clean.csv  # 54,837 rows (generated)
├── sql/
│   ├── schema.sql                # PostgreSQL DDL: staging + star schema + indexes
│   ├── cleaning.sql              # ETL with data-quality report
│   ├── dashboard_views.sql       # 7 commented, optimised dashboard views
│   └── validate_sqlite.py        # executes a SQLite adaptation of the SQL logic
│                                 # against the real CSVs; cross-checks vs clean_data.py
├── powerbi/build_guide.md        # step-by-step build: model, 8 visuals, DAX block
├── excel/pivot_guide.md          # Excel PivotTable equivalents + formulas
├── preview/
│   ├── make_preview.py           # generates the mock from the cleaned CSV
│   └── dashboard_preview.png     # 2×2 reference mock (labelled as such)
├── requirements.txt
└── .gitignore
```

## How to reproduce

```bash
pip install -r requirements.txt

# 1. Generate + clean the data
python3 data/generate_data.py     # → data/raw/ecommerce_orders.csv (58,000 rows)
python3 data/clean_data.py        # → data/final/ecommerce_sales_clean.csv (54,837 rows)

# 2. Prove the SQL layer runs (SQLite adaptation; committed .sql is PostgreSQL)
python3 sql/validate_sqlite.py    # ALL CHECKS PASSED

# 3. (Optional) full PostgreSQL run
# psql -f sql/schema.sql
# COPY raw_orders FROM 'data/raw/ecommerce_orders.csv' WITH (FORMAT csv, HEADER true);
# psql -f sql/cleaning.sql -f sql/dashboard_views.sql

# 4. Build the dashboard → follow powerbi/build_guide.md (~30 min)
#    Excel-only route → follow excel/pivot_guide.md

# 5. Regenerate the reference mock
python3 preview/make_preview.py
```

## Dataset description

`data/raw/ecommerce_orders.csv` — 58,000 rows × 15 columns, seeded (`42`) and
reproducible:

| Column | Description |
|---|---|
| `order_id` | Unique order id (`ORD-100001` …) |
| `order_date` | 2023-01-01 … 2025-09-30, weighted to Diwali/year-end peaks |
| `region` / `state` / `city` | North/South/East/West/Central India → 20 states, 31 cities |
| `product_category` / `product_name` | Electronics, Fashion, Home & Kitchen, Beauty, Sports (50 products) |
| `quantity`, `unit_price`, `discount_pct` | Qty 1–5; category-realistic INR prices; discounts 0–45% |
| `customer_id`, `customer_age_group`, `customer_gender` | 16k customers, repeat-purchase behaviour |
| `payment_method` | UPI, Cash on Delivery, cards, Net Banking, Wallet |
| `order_status` | Delivered (90%) / Cancelled (6%) / Returned (4%) |

~5.5% of raw rows are intentionally dirty (exact duplicates, nulls, negative
quantities, zero prices, >100% discounts, malformed dates, invalid regions,
case/whitespace noise) so the cleaning step is real. The ETL rejects them and
reports the rejection rate (`cleaning.sql` ends with a data-quality query).

`data/final/ecommerce_sales_clean.csv` adds the derived columns
`net_revenue = quantity × unit_price × (1 − discount_pct/100)` and `order_month`.

## The SQL layer

- **`schema.sql`** — `raw_orders` staging (all `TEXT`, so dirty rows load without
  cast errors) → `dim_customers`, `dim_products`, `fact_sales` star schema with
  PK/FK constraints, `CHECK`s, and 6 indexes matched to the dashboard's access
  patterns (monthly rollups, regional slicer, product/customer joins,
  delivered-only filter).
- **`cleaning.sql`** — regex-guarded casts (one bad value can't abort the load),
  `SELECT DISTINCT` dedupe, validity filters, surrogate-key dimension loads,
  and the fact insert; ends with a raw→clean row-count / rejection-% report.
- **`dashboard_views.sql`** — 7 views, each with an optimisation comment:
  monthly revenue by region, top-20 products, customer demographics, YoY growth
  (`LAG(...,12)` over a pre-aggregated 33-row CTE — never over the fact),
  category share, payment-method mix, discount-vs-margin impact.
  All revenue metrics filter `order_status = 'Delivered'`.
- **`validate_sqlite.py`** — no Postgres server needed: runs a SQLite adaptation
  of the same logic against the real CSVs and cross-checks it against
  `data/clean_data.py` (identical 54,837 rows; revenue within ₹1,000 on ₹648M —
  the residual is SQLite-vs-numpy half-cent rounding, documented in the script).

## What was verified vs. what wasn't

- ✅ Data generator runs; 58,000 raw rows confirmed
- ✅ Cleaning runs; 54,837 cleaned rows, 0 nulls, all validity rules hold
- ✅ SQL logic executes (SQLite adaptation) and converges with the Python
  pipeline on row counts, revenue, regions, and top product
- ✅ All insight numbers in this README were computed from the cleaned CSV —
  none invented
- ✅ Preview mock rendered from the real cleaned data and labelled as a mock
- ⚠️ The Power BI `.pbix` itself was not built here (Windows-only binary);
  the build guide + DAX are provided to reproduce it exactly
- ⚠️ Figures describe the synthetic dataset, not a real business
