#!/usr/bin/env python3
"""Build preview/dashboard_preview.png — a 2x2 matplotlib figure of the four
headline visuals, computed from the REAL cleaned CSV.

This is a REFERENCE MOCK for what the Power BI dashboard should show
(see powerbi/build_guide.md). It is not a Power BI screenshot.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "final" / "ecommerce_sales_clean.csv"
OUT = ROOT / "preview" / "dashboard_preview.png"

df = pd.read_csv(CLEAN, parse_dates=["order_date", "order_month"])
d = df[df.order_status == "Delivered"].copy()

plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold"})
fig, ax = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(
    "E-Commerce Sales Performance — reference mock (matplotlib, same cleaned data)\n"
    "Rebuild these four visuals in Power BI following powerbi/build_guide.md",
    fontsize=13, fontweight="bold", y=0.98)

# 1. monthly revenue trend by region
ax1 = ax[0, 0]
trend = d.groupby(["order_month", "region"]).net_revenue.sum().unstack() / 1e7
for region in ["North", "South", "East", "West", "Central"]:
    ax1.plot(trend.index, trend[region], marker="o", ms=3, label=region)
ax1.set_title("Monthly revenue trend by region (₹ cr)")
ax1.set_ylabel("Revenue (₹ cr)")
ax1.legend(ncols=5, fontsize=8, loc="upper left")
ax1.tick_params(axis="x", labelrotation=30, labelsize=7)
ax1.grid(alpha=0.3)

# 2. top 10 products
ax2 = ax[0, 1]
top10 = d.groupby("product_name").net_revenue.sum().nlargest(10).sort_values() / 1e5
ax2.barh(top10.index, top10.values, color="#1f77b4")
ax2.set_title("Top 10 products by revenue (₹ lakh)")
ax2.set_xlabel("Revenue (₹ lakh)")
for i, v in enumerate(top10.values):
    ax2.text(v, i, f" {v:,.0f}", va="center", fontsize=8)

# 3. category share donut
ax3 = ax[1, 0]
share = d.groupby("product_category").net_revenue.sum().sort_values(ascending=False)
wedges, texts, autotexts = ax3.pie(
    share.values, labels=share.index, autopct="%1.1f%%",
    startangle=90, pctdistance=0.8,
    wedgeprops=dict(width=0.4, edgecolor="white"))
ax3.set_title("Revenue share by category")

# 4. demographics stacked bar
ax4 = ax[1, 1]
demo = d.groupby(["customer_age_group", "customer_gender"]).net_revenue.sum().unstack() / 1e7
demo = demo.reindex(["18-25", "26-35", "36-45", "46-60"])
demo.plot(kind="bar", stacked=True, ax=ax4, color=["#1f77b4", "#ff7f0e"])
ax4.set_title("Revenue by age group × gender (₹ cr)")
ax4.set_ylabel("Revenue (₹ cr)")
ax4.set_xlabel("Age group")
ax4.tick_params(axis="x", labelrotation=0)
ax4.legend(title="Gender", fontsize=8)

fig.tight_layout(rect=[0, 0, 1, 0.93])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150)
print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
