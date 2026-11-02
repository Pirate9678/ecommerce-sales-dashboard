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
"""
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw" / "ecommerce_orders.csv"
OUT = BASE / "final" / "ecommerce_sales_clean.csv"
VALID_REGIONS = {"North", "South", "East", "West", "Central"}


def main():
    df = pd.read_csv(RAW, dtype=str)
    n_raw = len(df)

    # 1. standardise text
    for c in ["region", "state", "city", "product_category", "product_name",
              "customer_age_group", "customer_gender", "payment_method",
              "order_status", "customer_id", "order_id"]:
        df[c] = df[c].str.strip()
    df["region"] = df["region"].str.title()
    df["product_category"] = df["product_category"].str.title()

    # 2. cast
    df["order_date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d",
                                      errors="coerce").dt.date
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"],
                                       errors="coerce").fillna(0).clip(0, 80)

    # 3. dedupe on standardised/cast values (== SELECT DISTINCT in cleaning.sql)
    df = df.drop_duplicates(keep="first")

    # 4. validity filters
    df = df.dropna(subset=["order_date"])
    df = df.dropna(subset=["quantity", "unit_price"])
    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0)]
    df["quantity"] = df["quantity"].astype(int)
    df = df[df["region"].isin(VALID_REGIONS)]
    df = df.dropna(subset=["customer_id"])
    df = df[df["customer_id"] != ""]

    # 5. derived columns
    df["net_revenue"] = (df["quantity"] * df["unit_price"]
                         * (1 - df["discount_pct"] / 100)).round(2)
    df["order_month"] = pd.to_datetime(df["order_date"]).dt.to_period("M") \
        .dt.to_timestamp().dt.date

    df = df.sort_values(["order_date", "order_id"]).reset_index(drop=True)
    df["order_date"] = df["order_date"].astype(str)
    df["order_month"] = df["order_month"].astype(str)

    cols = ["order_id", "order_date", "order_month", "region", "state", "city",
            "product_category", "product_name", "quantity", "unit_price",
            "discount_pct", "net_revenue", "customer_id", "customer_age_group",
            "customer_gender", "payment_method", "order_status"]
    df = df[cols]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"raw={n_raw:,} -> cleaned={len(df):,} "
          f"({n_raw - len(df):,} rows removed, "
          f"{(n_raw - len(df)) / n_raw:.1%} dirty)")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
