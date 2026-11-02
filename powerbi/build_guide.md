# Power BI Build Guide — E-Commerce Sales Performance Dashboard

Rebuild the dashboard in **~30 minutes**. No `.pbix` is committed to this repo
(Power BI Desktop is Windows-only and `.pbix` is a binary); everything below is
exact enough to reproduce the dashboard 1:1 from the data in this repo.
`preview/dashboard_preview.png` shows the four headline visuals as a reference
mock rendered from the same cleaned data.

**Convention used everywhere:** revenue KPIs count **Delivered** orders only.
Returned/Cancelled rows stay in the data for ops views but must not inflate
sales numbers (this matches `sql/dashboard_views.sql`).

---

## 1. Get the data in

**Option A — CSV (fastest, recommended):**
1. Power BI Desktop → **Home → Get Data → Text/CSV**
2. Select `data/final/ecommerce_sales_clean.csv` → **Load**.
3. In **Power Query** (Transform Data), set types once:
   `order_date` → Date, `order_month` → Date, `quantity` → Whole Number,
   `unit_price` / `discount_pct` / `net_revenue` → Decimal Number.
   (The file is already clean; this is just type hygiene.)

**Option B — PostgreSQL (mirrors the SQL layer):**
1. Run, in order: `sql/schema.sql`, then load the raw CSV —
   `COPY raw_orders FROM '<repo>/data/raw/ecommerce_orders.csv' WITH (FORMAT csv, HEADER true);`
   then `sql/cleaning.sql`, then `sql/dashboard_views.sql`.
2. Get Data → PostgreSQL database → import `fact_sales`, `dim_customers`,
   `dim_products` (DirectQuery also works; Import is faster for this size).

## 2. Data model

**CSV path (single table):** rename the table to `Sales`.

**Postgres path (star schema):**
```
dim_customers (1) ───< (∞) fact_sales (∞) >─── (1) dim_products
         customer_key = customer_key      product_key = product_key
```
Power BI auto-detects these on the key columns; verify both relationships are
single-direction (`1 → ∞`).

**Calendar table (needed for YoY time intelligence — both paths):**
Modeling → New Table, paste:
```dax
Calendar =
ADDCOLUMNS(
    CALENDAR(DATE(2023, 1, 1), DATE(2025, 9, 30)),
    "Year", YEAR([Date]),
    "MonthNo", MONTH([Date]),
    "Month", FORMAT([Date], "mmm yyyy"),
    "YearMonth", FORMAT([Date], "yyyy-mm")
)
```
Relate `Calendar[Date] (1)` → `Sales[order_date] (∞)` (or `fact_sales[order_date]`),
single direction. Mark as date table: right-click `Calendar` → **Mark as date table**
→ choose `Date`. In the `Calendar` table, sort `Month` by `YearMonth`
(**Sort by Column**).

## 3. DAX measures (Modeling → New Measure, paste the whole block)

```dax
-- Base revenue: Delivered orders only (the dashboard's core convention)
Total Revenue =
CALCULATE (
    SUM ( Sales[net_revenue] ),
    Sales[order_status] = "Delivered"
)

Total Orders =
CALCULATE (
    COUNTROWS ( Sales ),
    Sales[order_status] = "Delivered"
)

AOV = DIVIDE ( [Total Revenue], [Total Orders], 0 )

-- Time intelligence (requires the Calendar table + relationship above)
Revenue PY =
CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( 'Calendar'[Date] ) )

YoY Growth % = DIVIDE ( [Total Revenue] - [Revenue PY], [Revenue PY], 0 )

-- Supporting measures used by the discount visual
Avg Discount % = AVERAGE ( Sales[discount_pct] )

Total Customers =
CALCULATE ( DISTINCTCOUNT ( Sales[customer_id] ), Sales[order_status] = "Delivered" )
```

> Postgres/star-schema path: replace `Sales[...]` with `fact_sales[...]` and
> `Sales[customer_id]` with `RELATED(dim_customers[customer_id])` inside
> `Total Customers`. The five core measures are otherwise identical.

Format: `Total Revenue` → Currency ₹, English (India); `AOV` → ₹, 0 decimals;
`YoY Growth %` → Percentage, 1 decimal.

## 4. Build the 8 visuals (one dashboard page, 16:9)

**Visual 1–3 — KPI cards** (Insert → Cards → New card visual)
| Card | Measure | Subtitle / tip |
|---|---|---|
| Total Revenue | `[Total Revenue]` | Callout value, category label off |
| Total Orders | `[Total Orders]` | |
| Avg Order Value | `[AOV]` | |
Add a 4th card with `[YoY Growth %]` filtered to the latest full year if you like;
conditional-format its data label green/red.

**Visual 4 — Line chart: monthly revenue trend by region**
- X-axis: `Calendar[Month]` (sort by `YearMonth`)
- Y-axis: `[Total Revenue]`
- Legend: `Sales[region]`
- Expect: clear Oct–Nov (Diwali) and December spikes every year — see the mock.

**Visual 5 — Bar chart: Top 10 products by revenue**
- Y-axis: `Sales[product_name]`, X-axis: `[Total Revenue]`
- Filters on visual → Top N: Top **10** by `[Total Revenue]`
- Sort descending. Expect HP Laptop 15s on top (~₹1.45 cr).

**Visual 6 — Donut chart: revenue share by category**
- Legend: `Sales[product_category]`, Values: `[Total Revenue]`
- Turn on **Detail labels → Percent of total**. Expect Electronics ≈ 66%.

**Visual 7 — Stacked bar: revenue by age group × gender**
- X-axis: `Sales[customer_age_group]`, Y-axis: `[Total Revenue]`
- Legend: `Sales[customer_gender]`
- Sort X-axis: 18-25, 26-35, 36-45, 46-60. Expect 26-35 as the tallest stack.

**Visual 8 — Map: revenue by state**
- Use the **Filled map** visual; Location: `Sales[state]`, Tooltips: `[Total Revenue]`.
- If the filled map misplaces Indian states, switch to the **Azure Map** visual
  (same fields). Bubble size or color saturation = revenue.

**Slicers (top of the page):**
- `Calendar[Year]` → dropdown or button slicer (multi-select)
- `Sales[region]` → horizontal buttons
- `Sales[product_category]` → dropdown
- Optional: `Calendar[Month]` for month-level drill.

Set **Edit interactions** so slicers filter all 8 visuals; turn off the map's
cross-filtering of the KPI cards if you want KPIs to stay global (optional).

## 5. Sanity checks (numbers you should see)

After building, with no slicers applied:
- Total Revenue ≈ **₹64.77 cr**, Total Orders ≈ **49,286**, AOV ≈ **₹13,141**
- Top region **South** (≈25%), top category **Electronics** (≈66.5%)
- Best month **Nov 2024** (≈₹2.69 cr)
- UPI ≈ **38%** of delivered orders

If a number is off, the usual culprit is the `Delivered` filter missing from a
measure, or the Calendar relationship not marked as the date table.

## 6. Publish (optional)

File → Publish → your Power BI workspace → share the link / schedule refresh.
For auto-refresh, point the dataset at the Postgres Option B instead of the CSV.
