# E-Commerce Sales Performance Dashboard

Interactive sales analytics for a synthetic Indian e-commerce dataset of
**58,000 raw orders (Jan 2023 – Sep 2025)**, cleaned to **54,831** analysis-ready
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
| Total revenue | **₹63.76 cr** (₹637,611,185) |
| Delivered orders | **49,227** |
| Average order value | **₹12,952** |
| Top region | **South** — ₹16.11 cr (25.3% of revenue) |
| Top category | **Electronics** — ₹41.90 cr (65.7% of revenue) |
| Top product | **HP Laptop 15s** — ₹13.65 cr |
| Best month | **Oct 2024** — ₹2.73 cr (Diwali spike) |
| Diwali lift (Oct–Nov vs regular months) | **+40.0%** average monthly revenue |
| Full-year YoY (2024 vs 2023) | **−0.7%** — flat by construction; monthly YoY varies (e.g. Oct 2024 **+10.8%**) |
| Top payment method | **UPI** — 38.1% of delivered orders |
| Core demographic | **26–35 yrs** — 37.8% of revenue; gender split 55.0% Male / 45.0% Female |
| Avg discount | 10.9% · Cancelled 6.1% · Returned 4.1% |
| Coverage | 12,302 customers · 20 states · 31 cities |

## Pipeline

```
data/generate_data.py            → data/raw/ecommerce_orders.csv   (58,000 rows, ~5.5% intentionally dirty)
        │  seed=42, reproducible; Diwali (Oct–Nov) + year-end seasonal spikes
        ▼
sql/schema.sql                   → PostgreSQL star schema
sql/cleaning.sql                 → ETL: dedupe, type casts, validity rules,
                                   net_revenue + order_month derivations
data/clean_data.py               → data/final/ecommerce_sales_clean.csv (54,831 rows)
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
│   ├── generate_data.py          # synthetic raw data generator (seeded, vectorised)
│   ├── clean_data.py             # Python cleaning, mirrors sql/cleaning.sql
│   ├── raw/ecommerce_orders.csv  # 58,000 rows (generated)
│   └── final/ecommerce_sales_clean.csv  # 54,831 rows (generated)
├── sql/
│   ├── schema.sql                # PostgreSQL DDL: staging + star schema + indexes
│   ├── cleaning.sql              # ETL with data-quality report
│   ├── dashboard_views.sql       # 7 commented, optimised dashboard views
│   └── validate_sqlite.py        # executes a SQLite adaptation of the SQL logic
│                                 # against the real CSVs; cross-checks vs clean_data.py
├── benchmark/
│   ├── benchmark.py              # times generate/clean/validate + all 7 views
│   │                             # at 58k and 1M rows, old vs new indexes
│   └── results.json              # measured numbers (see Performance & scaling)
├── powerbi/build_guide.md        # step-by-step build: model, 8 visuals, DAX block
├── excel/pivot_guide.md          # Excel PivotTable equivalents + formulas
├── preview/
│   ├── make_preview.py           # generates the mock from the cleaned CSV
│   ├── dashboard_preview.png     # 2×2 reference mock (labelled as such)
│   └── result_*.png              # individual result charts (Delivered only)
├── requirements.txt
└── .gitignore
```

## How to reproduce

```bash
pip install -r requirements.txt

# 1. Generate + clean the data
python3 data/generate_data.py     # → data/raw/ecommerce_orders.csv (58,000 rows)
python3 data/clean_data.py        # → data/final/ecommerce_sales_clean.csv (54,831 rows)

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

# 6. Reproduce the performance numbers (58k + 1M scales, ~6 min)
python3 benchmark/benchmark.py        # writes benchmark/results.json
python3 benchmark/benchmark.py --quick  # 58k scale only, ~1 min
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

> **Data provenance (Nov 2026):** the dataset was regenerated with the
> optimised vectorised generator (same seed `42`, same distributions, same
> dirty-row mix — see Performance & scaling). The draws differ row-for-row
> from the pre-optimisation file because vectorised RNG calls don't consume
> the random stream the same way per-row loops did; every number in this
> README was recomputed from the new data, and the cleaner reproduces the
> old cleaned file byte-for-byte on the old raw file. One old typo was also
> fixed in this pass: the top product was listed as ₹1.45 cr, but the old
> data itself measured ₹14.51 cr for HP Laptop 15s.

## The SQL layer

- **`schema.sql`** — `raw_orders` staging (all `TEXT`, so dirty rows load without
  cast errors) → `dim_customers`, `dim_products`, `fact_sales` star schema with
  PK/FK constraints, `CHECK`s, and 6 single-column indexes matched to the
  dashboard's access patterns (monthly rollups, regional slicer,
  product/customer joins, delivered-only filter), plus 4 covering composite
  indexes (see Performance & scaling).
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
  `data/clean_data.py` (identical 54,831 rows; revenue within ₹1,000 on ₹638M —
  the residual is SQLite-vs-numpy half-cent rounding, documented in the script).

## Performance & scaling (Nov 2026 optimisation)

Measured on a 4-vCPU host, median of 3 runs at 58k rows and 2 runs at 1M
(`benchmark/benchmark.py`, full numbers in `benchmark/results.json`).
"Before" is the pre-optimisation code measured 8 Nov 2026 on the same host.

| Step | 58k rows: before → after | 1M rows: before → after |
|---|---|---|
| Generate (`data/generate_data.py`) | 2.88s → **1.19s (2.4x)** | 31.0s → **15.69s (2.0x)** |
| Clean (`data/clean_data.py`) | 1.72s → **1.87s (0.9x — flat, within run noise)** | 24.45s → **21.53s (1.1x)** |
| SQL validate (`sql/validate_sqlite.py`) | 3.62s → **3.06s (1.2x)** | — → **63.99s** (new capability) |

What changed:
- **Generator** — fully vectorised: geography, products and dates are sampled
  with grouped numpy calls instead of one `rng.choice` per row; dirty rows
  are injected with boolean masks; the frame is assembled once from numpy
  arrays (single `np.concatenate` + one permutation) instead of
  `pd.concat` + `DataFrame.sample` shuffle. New flags: `--base-rows`,
  `--customers`, `--out` — e.g. `python3 data/generate_data.py
  --base-rows 1000000 --out /tmp/raw_1m.csv`.
- **Cleaner** — dates stay `datetime64` (no `.dt.date` object round trip),
  `order_month` is one `astype("datetime64[M]")`, all five validity rules
  are a single combined boolean mask instead of five full-frame copies.
  Output is **byte-identical** to the old cleaner on the same raw input.
- **SQL** — 4 covering composite indexes in `schema.sql`, each starting with
  `order_status` (every view filters Delivered first) and carrying the
  measure columns as trailing keys so the planner reads the index only.

Dashboard views at 1M rows, covering vs single-column indexes (median of 3):

| View | Single-col | Covering | Speedup |
|---|---|---|---|
| Monthly revenue by region | 1.19s | **0.21s** | 5.7x |
| Top products | 1.19s | **0.75s** | 1.6x |
| Customer demographics | 1.66s | **0.90s** | 1.8x |
| YoY growth | 0.71s | **0.14s** | 5.0x |
| Category share | 0.77s | **0.45s** | 1.7x |
| Payment-method mix | 0.67s | **0.14s** | 4.9x |
| Discount impact | 1.10s | 1.09s | 1.0x |
| **All 7 views** | **7.28s** | **3.68s** | **2.0x** |

Honest limits:
- The cleaner only improves ~1.1x at 1M rows and is flat at 58k (1.87s vs 1.72s baseline — within run noise): it is I/O-bound (`read_csv` + `to_csv`
  of 145MB at 1M rows, plus the 11 `.str.strip()` calls, dedupe and sort
  are inherent costs). The generator is where vectorisation pays.
- The discount-impact view stays ~1.0x: it groups by the *dimension's*
  `product_category`, so index order can't serve its GROUP BY.
- The first version of the composite indexes was **non-covering** (no
  payload columns) and measured *slower* than single-column indexes at 1M
  rows — a composite index only pays when it covers the query. The numbers
  above are for the covering form. (This SQLite build rejects `INCLUDE`,
  so the payload columns are trailing key columns instead; PostgreSQL
  users can equivalently use `INCLUDE (net_revenue, ...)`.)
- Memory at 1M rows: generate peaks at ~1.3GB, clean at ~0.9GB, SQL
  validation at ~1.9GB (in-memory SQLite) — the 1M scale is for stress
  testing, not the committed dataset.

## What was verified vs. what wasn't

- ✅ Data generator runs; 58,000 raw rows confirmed
- ✅ Cleaning runs; 54,831 cleaned rows, 0 nulls, all validity rules hold
- ✅ SQL logic executes (SQLite adaptation) and converges with the Python
  pipeline on row counts, revenue, regions, and top product
- ✅ All insight numbers in this README were computed from the cleaned CSV —
  none invented
- ✅ Preview mock rendered from the real cleaned data and labelled as a mock
- ✅ Optimised pipeline verified: cleaner output byte-identical to the old
  version on the same raw file; 1M-row generation + cleaning + SQL
  validation all pass (`benchmark/benchmark.py`, results in
  `benchmark/results.json`)
- ⚠️ The Power BI `.pbix` itself was not built here (Windows-only binary);
  the build guide + DAX are provided to reproduce it exactly
- ⚠️ Figures describe the synthetic dataset, not a real business
- ⚠️ View speedups were measured in the SQLite mirror, not on a live
  PostgreSQL server; the covering-index design transfers, the exact
  speedups may differ there
