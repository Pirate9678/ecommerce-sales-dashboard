#!/usr/bin/env python3
"""
Clean the raw e-commerce orders and write the analysis-ready file.

Mirrors sql/cleaning.sql rule-for-rule AND in the same order:
  1. Standardise text: trim whitespace, fix case.
  2. Cast: order_date -> date (invalid -> NaT), quantity/unit_price -> numeric,
     discount_pct -> numeric with missing -> 0, clipped to [0, 80].
  3. Drop exact duplicate rows on the standardised/cast values (keep first)
     -- this matches SQL's SELECT DISTINCT, which also runs after casting,
     -- so e.g. a blank discount (coerced to 0) colliding with a real 0
     -- is deduped in both pipelines.
  4. Validity filters: order_date present; quantity/unit_price present and > 0;
     region in {North, South, East, West, Central}; customer_id present.
  5. Derived: net_revenue = quantity*unit_price*(1-discount_pct/100),
              order_month = first day of order month.

Output: data/final/ecommerce_sales_clean.csv

OPTIMISED (Nov 2026): the old version converted dates to Python ``date``
objects (``.dt.date``) and derived order_month through
``to_period("M").dt.to_timestamp().dt.date`` — object-dtype round trips
that dominated runtime — and applied its five validity filters as five
separate copies of the whole frame. This version keeps dates as datetime64
throughout, derives order_month with a single ``astype("datetime64[M]")``,
applies all validity rules as ONE combined boolean mask, and formats date
strings once, at write time, with a C-level datetime64->str conversion.
Output is byte-identical to the old version on the same raw input
(verified in benchmark/benchmark.py).

  python3 data/clean_data.py
  python3 data/clean_data.py --raw /tmp/raw_1m.csv --out /tmp/clean_1m.csv
"""
import argparse
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw" / "ecommerce_orders.csv"
OUT = BASE / "final" / "ecommerce_sales_clean.csv"
VALID_REGIONS = {"North", "South", "East", "West", "Central"}

TEXT_COLS = ["region", "state", "city", "product_category", "product_name",
             "customer_age_group", "customer_gender", "payment_method",
             "order_status", "customer_id", "order_id"]


def main():
    ap = argparse.ArgumentParser(description="Clean raw e-commerce orders.")
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    df = pd.read_csv(args.raw, dtype=str)
    n_raw = len(df)

    # 1. standardise text (vectorised str ops, unchanged from the old version)
    for c in TEXT_COLS:
        df[c] = df[c].str.strip()
    df["region"] = df["region"].str.title()
    df["product_category"] = df["product_category"].str.title()

    # 2. cast — dates stay datetime64 (no .dt.date object round trip)
    df["order_date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d",
                                      errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"],
                                       errors="coerce").fillna(0).clip(0, 80)

    # 3. dedupe on standardised/cast values (== SELECT DISTINCT in cleaning.sql)
    df = df.drop_duplicates(keep="first")

    # 4. validity filters — ONE combined mask, not five sequential copies:
    # each df[mask] copies the whole frame, so filtering in one pass is
    # ~4 full-frame copies cheaper at 1M rows.
    keep = (df["order_date"].notna()
            & df["quantity"].notna() & df["unit_price"].notna()
            & (df["quantity"] > 0) & (df["unit_price"] > 0)
            & df["region"].isin(VALID_REGIONS)
            & df["customer_id"].notna() & (df["customer_id"] != ""))
    df = df[keep]
    df["quantity"] = df["quantity"].astype(int)

    # 5. derived columns
    df["net_revenue"] = (df["quantity"] * df["unit_price"]
                         * (1 - df["discount_pct"] / 100)).round(2)
    # datetime64[M] truncates to the first of the month in one vectorised op
    df["order_month"] = df["order_date"].values.astype("datetime64[M]")

    df = df.sort_values(["order_date", "order_id"]).reset_index(drop=True)

    # Format dates to strings only now, at write time. datetime64 -> str is
    # a C-level conversion and produces the identical 'YYYY-MM-DD' strings
    # as the old version's .astype(str) on date objects (NaT rows are
    # already filtered out, so no 'NaT' string can leak in).
    df["order_date"] = df["order_date"].values.astype("datetime64[D]").astype(str)
    df["order_month"] = df["order_month"].values.astype("datetime64[D]").astype(str)

    cols = ["order_id", "order_date", "order_month", "region", "state", "city",
            "product_category", "product_name", "quantity", "unit_price",
            "discount_pct", "net_revenue", "customer_id", "customer_age_group",
            "customer_gender", "payment_method", "order_status"]
    df = df[cols]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"raw={n_raw:,} -> cleaned={len(df):,} "
          f"({n_raw - len(df):,} rows removed, "
          f"{(n_raw - len(df)) / n_raw:.1%} dirty)")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
