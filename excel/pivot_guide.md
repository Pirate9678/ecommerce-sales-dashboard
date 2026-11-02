# Excel Pivot Guide — same dashboard summaries from the cleaned CSV

You can reproduce every headline number of the Power BI dashboard in Excel
from `data/final/ecommerce_sales_clean.csv` — no Power BI licence needed.
Open the CSV in Excel (Data → From Text/CSV), load it into a Table
(`Ctrl+T`, name it `Sales`), and build the pivots below.

**Global rule (matches the SQL views and DAX):** revenue metrics count
**Delivered** orders only. Either filter `order_status = Delivered` in each
pivot, or add a helper column once:

```
net_revenue_delivered = =IF([@order_status]="Delivered", [@net_revenue], 0)
```

All formulas below assume the `Sales` table and summarise that helper column.

---

## 1. KPI cards (single cells)

| KPI | Formula |
|---|---|
| Total revenue | `=SUM(Sales[net_revenue_delivered])` → **₹64,76,84,938** |
| Delivered orders | `=COUNTIF(Sales[order_status],"Delivered")` → **49,286** |
| AOV | `=SUM(Sales[net_revenue_delivered])/COUNTIF(Sales[order_status],"Delivered")` → **₹13,141** |
| YoY growth (2024 vs 2023) | `=(SUMIFS(...2024...)-SUMIFS(...2023...))/SUMIFS(...2023...)` → **~0%** (flat by construction; monthly YoY varies) |

Year-filtered revenue with SUMIFS (assumes `order_month` is a real date):
```
=SUMIFS(Sales[net_revenue_delivered], Sales[order_status], "Delivered",
        Sales[order_month], ">="&DATE(2024,1,1), Sales[order_month], "<"&DATE(2025,1,1))
```

## 2. PivotTables (Insert → PivotTable, tick "Add to Data Model" if you want DISTINCTCOUNT)

**a) Monthly revenue by region** (line chart)
- Rows: `order_month` → group by Months (right-click → Group → Months + Years)
- Columns: `region`
- Values: Sum of `net_revenue_delivered`
- Insert → Line chart. Oct–Nov Diwali spikes should stand out.

**b) Top 10 products** (bar chart)
- Rows: `product_name`, Values: Sum of `net_revenue_delivered`
- Sort descending → Right-click product → Filter → Top 10 → Top 10 by Sum
- Insert → Bar chart. Expect HP Laptop 15s ≈ ₹1.45 cr.

**c) Category share** (donut)
- Rows: `product_category`, Values: Sum of `net_revenue_delivered`
- Show Values As → **% of Grand Total**; Insert → Doughnut chart.

**d) Demographics** (stacked bar)
- Rows: `customer_age_group`, Columns: `customer_gender`
- Values: Sum of `net_revenue_delivered` → Insert → Stacked Column chart.

**e) Payment-method mix**
- Rows: `payment_method`, Values: Count of `order_id` + Sum of `net_revenue_delivered`;
  second value → Show Values As → % of Grand Total.

**f) Discount impact by category**
- Rows: `product_category`
- Values: Average of `discount_pct`, Sum of `net_revenue_delivered`
- Add calculated field for margin proxy:
  `= 1 - SUM(discount_given)/SUM(gross)` — or compute per-row helper columns
  `gross = [@quantity]*[@unit_price]` and `discount_inr = [@gross]*[@discount_pct]/100`,
  then pivot Sum of both.

## 3. Slicers (the interactive part)

With any pivot selected: PivotTable Analyze → Insert Slicer →
`order_month` (Timeline is nicer: Insert Timeline), `region`, `product_category`.
Right-click each slicer → **Report Connections** → tick all pivots so one click
filters the whole dashboard.

## 4. Refresh workflow (the "30% faster reporting" loop)

Next week: replace the CSV, Data → Refresh All. Because the cleaning logic lives
in `data/clean_data.py` / `sql/cleaning.sql` (not in manual spreadsheet edits),
the weekly refresh is: regenerate → clean → refresh — no rework.
