#!/usr/bin/env python3
"""
Generate the raw e-commerce orders dataset for the
"E-Commerce Sales Performance Dashboard" project.

Output: data/raw/ecommerce_orders.csv  (~58,000 rows at the default size)

The raw file is INTENTIONALLY dirty (duplicates, nulls, invalid values,
case/whitespace inconsistencies ~= 7% of rows) so the SQL/Python cleaning
step (sql/cleaning.sql, data/clean_data.py) has real work to do.

Reproducible: fixed seed (SEED = 42).

OPTIMISED (Nov 2026): the original version sampled every row with Python
loops (one rng.choice per customer for geography, one per order for product
and date) — ~2.9 s for 58k rows and unusable at 1M rows. This version is
fully vectorised: geography, products and dates are sampled with grouped
numpy calls, dirty-row injection uses boolean masks instead of per-row
.iloc writes, and date strings are built with one vectorised
pd.to_datetime call. Same distributions, same dirty-row mix, same seed —
but ~10x faster at 58k rows and able to generate 1M+ rows in seconds
(see benchmark/benchmark.py).

  python3 data/generate_data.py                  # default 54k base rows
  python3 data/generate_data.py --base-rows 1000000 --out /tmp/raw_1m.csv

NOTE: vectorised RNG calls do not draw the same values as the old per-row
loops, so the regenerated data differs row-for-row from the pre-optimisation
file (same seed, same distributions, same dirty mix). All downstream
numbers (README insights, preview) were recomputed from the new data.
"""
import argparse
import calendar
import numpy as np
import pandas as pd
from pathlib import Path

SEED = 42
N_BASE = 54_000        # clean base orders
N_DIRTY = 4_000        # intentionally dirty rows appended on top
OUT = Path(__file__).resolve().parent / "raw" / "ecommerce_orders.csv"

# ---------------------------------------------------------------- regions
REGION_MAP = {
    "North": {
        "Delhi": ["New Delhi"],
        "Uttar Pradesh": ["Lucknow", "Kanpur", "Noida"],
        "Punjab": ["Ludhiana", "Amritsar"],
        "Haryana": ["Gurugram", "Faridabad"],
        "Rajasthan": ["Jaipur"],
    },
    "South": {
        "Karnataka": ["Bengaluru", "Mysuru"],
        "Tamil Nadu": ["Chennai", "Coimbatore"],
        "Telangana": ["Hyderabad"],
        "Kerala": ["Kochi"],
        "Andhra Pradesh": ["Vijayawada"],
    },
    "East": {
        "West Bengal": ["Kolkata", "Howrah"],
        "Bihar": ["Patna"],
        "Odisha": ["Bhubaneswar"],
        "Assam": ["Guwahati"],
        "Jharkhand": ["Ranchi"],
    },
    "West": {
        "Maharashtra": ["Mumbai", "Pune", "Nagpur"],
        "Gujarat": ["Ahmedabad", "Surat"],
        "Goa": ["Panaji"],
    },
    "Central": {
        "Madhya Pradesh": ["Bhopal", "Indore"],
        "Chhattisgarh": ["Raipur"],
    },
}
REGION_W = {"North": 0.24, "South": 0.26, "West": 0.24, "East": 0.14, "Central": 0.12}
REGIONS = list(REGION_MAP)

# Precompute per-region (state, city) pairs with the sampling weights that
# reproduce the old two-step draw: state uniform within the region, then
# city uniform within the state  =>  P(state, city) = 1/n_states * 1/n_cities.
REGION_PAIRS = {}
for _r, _states in REGION_MAP.items():
    _pairs = [(s, c) for s, cities in _states.items() for c in cities]
    _w = np.array([1.0 / len(_states) / len(_states[s]) for s, _ in _pairs])
    REGION_PAIRS[_r] = (
        np.array([s for s, _ in _pairs]),
        np.array([c for _, c in _pairs]),
        _w,
    )

# --------------------------------------------------------------- products
# product_name -> base unit price (INR). Jittered +/-15% per order.
PRODUCTS = {
    "Electronics": {
        "boAt Wireless Headphones": 1999, "Samsung Galaxy Smartphone": 24999,
        "HP Laptop 15s": 58990, "Mi Smart TV 43 inch": 27999,
        "Noise Smartwatch": 2999, "Sony Bluetooth Speaker": 8990,
        "Canon Inkjet Printer": 9499, "Logitech Wireless Mouse": 1295,
        "SanDisk 128GB Pendrive": 1499, "Daikin 1.5T Split AC": 41990,
    },
    "Fashion": {
        "Roadster Cotton T-Shirt": 499, "Levi's 511 Slim Jeans": 2799,
        "Nike Running Shoes": 5995, "Zara Floral Dress": 2490,
        "Puma Sports Jacket": 3499, "Biba Kurta Set": 1999,
        "Adidas Sneakers": 4999, "H&M Linen Shirt": 1499,
        "Manyavar Kurta Pyjama": 2999, "Bata Formal Shoes": 1899,
    },
    "Home & Kitchen": {
        "Prestige Induction Cooktop": 2895, "Wakefit Memory Foam Mattress": 8999,
        "Milton Thermosteel Flask": 999, "Philips Air Fryer": 11995,
        "Home Centre Bedsheet Set": 1499, "Pigeon Pressure Cooker": 1899,
        "Nilkamal Chairs Set of 4": 4999, "Borosil Dinner Set": 2499,
        "Dyson V12 Vacuum Cleaner": 52900, "Usha Ceiling Fan": 2499,
    },
    "Beauty": {
        "Lakme Absolute Lipstick": 749, "Mamaearth Face Wash": 349,
        "L'Oreal Shampoo 650ml": 599, "Nivea Body Lotion": 449,
        "Maybelline Foundation": 899, "Forest Essentials Face Cream": 1895,
        "Biotique Hair Oil": 299, "Sugar Eyeshadow Palette": 1199,
        "Dove Soap Pack of 4": 399, "Plum Niacinamide Serum": 799,
    },
    "Sports": {
        "Cosco Football": 899, "Yonex Badminton Racket": 2499,
        "Nivia Cricket Bat": 3299, "Boldfit Yoga Mat": 999,
        "Kobo Dumbbell Set 10kg": 1899, "Spalding Basketball": 1499,
        "Nike Gym Bag": 1995, "Hercules Mountain Bicycle": 14999,
        "SG Cricket Ball Pack": 699, "Strauss Skipping Rope": 299,
    },
}
CATEGORIES = list(PRODUCTS)
CAT_W = [0.30, 0.28, 0.18, 0.14, 0.10]  # Electronics, Fashion, H&K, Beauty, Sports
# Per-category product name / price lookup arrays (all categories have 10).
CAT_NAMES = {c: np.array(list(PRODUCTS[c].keys())) for c in CATEGORIES}
CAT_PRICES = {c: np.array(list(PRODUCTS[c].values()), dtype=float)
              for c in CATEGORIES}

# ------------------------------------------------------------- seasonality
# Monthly demand multipliers: Diwali (Oct-Nov) + year-end (Dec) spikes.
MONTH_W = {1: 0.90, 2: 0.75, 3: 0.85, 4: 0.90, 5: 0.95, 6: 0.80,
           7: 0.80, 8: 0.95, 9: 1.00, 10: 1.35, 11: 1.30, 12: 1.25}
PERIOD_MONTHS = [(y, m) for y in (2023, 2024) for m in range(1, 13)] + \
                [(2025, m) for m in range(1, 10)]          # 2023-01 .. 2025-09
PERIOD_YEAR = np.array([y for y, _ in PERIOD_MONTHS])
PERIOD_MONTH = np.array([m for _, m in PERIOD_MONTHS])
PERIOD_DAYS = np.array([calendar.monthrange(y, m)[1] for y, m in PERIOD_MONTHS])
PERIOD_W = np.array([MONTH_W[m] for _, m in PERIOD_MONTHS], dtype=float)
PERIOD_W /= PERIOD_W.sum()

AGE_GROUPS = ["18-25", "26-35", "36-45", "46-60"]
AGE_W = [0.28, 0.38, 0.22, 0.12]
GENDERS, GENDER_W = ["Male", "Female"], [0.54, 0.46]
PAYMENTS = ["UPI", "Cash on Delivery", "Credit Card", "Debit Card", "Net Banking", "Wallet"]
PAY_W = [0.38, 0.22, 0.15, 0.12, 0.08, 0.05]
STATUSES, STATUS_W = ["Delivered", "Cancelled", "Returned"], [0.90, 0.06, 0.04]


def sample_dates(n, rng):
    """Vectorised date sampling: period (weighted) -> day-of-month -> string.

    Old version looped per row with f-string formatting; this builds the
    whole column with three numpy calls + one vectorised to_datetime.
    Returns (date strings, month numbers) — the months feed the festival
    flag without re-parsing the strings.
    """
    idx = rng.choice(len(PERIOD_MONTHS), size=n, p=PERIOD_W)
    years = PERIOD_YEAR[idx]
    months = PERIOD_MONTH[idx]
    days = rng.integers(1, PERIOD_DAYS[idx] + 1)
    dates = pd.to_datetime(
        {"year": years, "month": months, "day": days}
    ).dt.strftime("%Y-%m-%d").to_numpy()
    return dates, months


def main():
    ap = argparse.ArgumentParser(description="Generate raw e-commerce orders.")
    ap.add_argument("--base-rows", type=int, default=N_BASE,
                    help="clean base orders (default 54,000)")
    ap.add_argument("--customers", type=int, default=16_000,
                    help="customers in the master table (default 16,000)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    n_base, n_cust = args.base_rows, args.customers
    rng = np.random.default_rng(args.seed)
    # Dirty rows scale with the base size (same ~7% mix as the default).
    scale = n_base / N_BASE
    n_dup = round(1500 * scale)
    n_nul = round(1200 * scale)
    n_inv = round(800 * scale)
    n_noi = round(500 * scale)

    # ---- customer master (arrays, not a DataFrame — indexed directly below)
    cust_regions = rng.choice(REGIONS, size=n_cust,
                              p=[REGION_W[r] for r in REGIONS])
    cust_state = np.empty(n_cust, dtype=object)
    cust_city = np.empty(n_cust, dtype=object)
    for r in REGIONS:  # one vectorised draw per region, not per customer
        m = cust_regions == r
        states, cities, w = REGION_PAIRS[r]
        k = rng.choice(len(states), size=int(m.sum()), p=w)
        cust_state[m] = states[k]
        cust_city[m] = cities[k]
    cust_ids = np.char.add("CUST-", np.char.zfill(
        (np.arange(n_cust) + 1).astype(str), 5))
    cust_age = rng.choice(AGE_GROUPS, size=n_cust, p=AGE_W)
    cust_gender = rng.choice(GENDERS, size=n_cust, p=GENDER_W)
    # power-law-ish repeat purchase propensity (a few customers buy a lot)
    propensity = rng.exponential(scale=1.0, size=n_cust)
    propensity /= propensity.sum()

    # ---- base orders
    cust_idx = rng.choice(n_cust, size=n_base, p=propensity)

    cats = rng.choice(CATEGORIES, size=n_base, p=CAT_W)
    prod_names = np.empty(n_base, dtype=object)
    base_prices = np.empty(n_base, dtype=float)
    for c in CATEGORIES:  # one vectorised draw per category, not per order
        m = cats == c
        k = rng.integers(0, len(CAT_NAMES[c]), size=int(m.sum()))
        prod_names[m] = CAT_NAMES[c][k]
        base_prices[m] = CAT_PRICES[c][k]

    order_date, order_month_num = sample_dates(n_base, rng)
    festival = np.isin(order_month_num, [10, 11, 12])

    qty = rng.choice([1, 2, 3, 4, 5], size=n_base, p=[0.55, 0.25, 0.12, 0.05, 0.03])
    unit_price = np.round(base_prices * rng.uniform(0.85, 1.15, n_base)).astype(int)
    disc = rng.beta(2, 5, n_base) * 40 + np.where(festival, 8, 0)
    disc = np.clip(disc, 0, 45).round(1)
    disc[rng.random(n_base) < 0.20] = 0.0  # no-discount orders

    # ---- base orders, as a dict of numpy arrays (one DataFrame is built
    # at the very end — building dirty parts as DataFrames and pd.concat-ing
    # them, as the old version did, copies the whole frame twice)
    base = {
        "order_id": np.char.add("ORD-", (np.arange(n_base) + 100001).astype(str)),
        "order_date": order_date,
        "region": cust_regions[cust_idx],
        "state": cust_state[cust_idx],
        "city": cust_city[cust_idx],
        "product_category": cats,
        "product_name": prod_names,
        # float64 on purpose: dirty parts inject NaN, so the final frame
        # upcasts anyway — and the CSV writes "1.0", as the old file did.
        "quantity": qty.astype(float),
        "unit_price": unit_price.astype(float),
        "discount_pct": disc,
        "customer_id": cust_ids[cust_idx],
        "customer_age_group": cust_age[cust_idx],
        "customer_gender": cust_gender[cust_idx],
        "payment_method": rng.choice(PAYMENTS, size=n_base, p=PAY_W),
        "order_status": rng.choice(STATUSES, size=n_base, p=STATUS_W),
    }
    COLS = list(base)
    # All text columns MUST be object dtype, not numpy's fixed-width unicode
    # (<U...): assigning np.nan into a <U array stringifies it to the literal
    # string 'nan' in the CSV, which pandas then misreads as NaN but SQLite
    # reads as a real customer_id/region 'nan' — that broke the SQL ETL's
    # dim_customers UNIQUE constraint (a phantom 'nan' customer with 8
    # different demographics). Object dtype keeps NaN a true null, exactly
    # as the old DataFrame-based version did.
    for _c in ("order_id", "order_date", "region", "state", "city",
               "product_category", "product_name", "customer_id",
               "customer_age_group", "customer_gender", "payment_method",
               "order_status"):
        base[_c] = base[_c].astype(object)

    def _sample_part(n_rows):
        """Copy of `n_rows` base rows, as a dict of arrays."""
        idx = rng.choice(n_base, size=n_rows, replace=False)
        return {c: base[c][idx].copy() for c in COLS}

    # ---- dirty rows (~7%): duplicates, nulls, invalids, case/whitespace noise
    parts = [base]
    # 1) exact duplicates
    parts.append(_sample_part(n_dup))
    # 2) nulls in key fields (discount nulls are fillable -> kept by cleaning)
    nul = _sample_part(n_nul)
    nul_fields = rng.choice(["order_date", "quantity", "unit_price", "region",
                             "customer_id", "discount_pct"], size=n_nul)
    for f in ("order_date", "quantity", "unit_price", "region",
              "customer_id", "discount_pct"):
        nul[f][nul_fields == f] = np.nan
    parts.append(nul)
    # 3) invalid values (one vectorised assignment per kind, not per row)
    inv = _sample_part(n_inv)
    inv_kind = rng.choice(["neg_qty", "zero_price", "huge_discount",
                           "bad_date", "bad_region"], size=n_inv)
    inv["quantity"][inv_kind == "neg_qty"] = \
        -rng.integers(1, 4, size=int((inv_kind == "neg_qty").sum()))
    inv["unit_price"][inv_kind == "zero_price"] = 0
    inv["discount_pct"][inv_kind == "huge_discount"] = 150.0
    inv["order_date"][inv_kind == "bad_date"] = "2024-13-45"
    inv["region"][inv_kind == "bad_region"] = rng.choice(
        ["N/A", "unknown", ""], size=int((inv_kind == "bad_region").sum()))
    parts.append(inv)
    # 4) case/whitespace noise (valid rows, standardised by cleaning)
    noi = _sample_part(n_noi)
    noi["region"] = pd.Series(noi["region"]).str.lower().str.pad(8, side="both") \
        .to_numpy(dtype=object)
    noi["product_category"] = pd.Series(noi["product_category"]).str.upper() \
        .to_numpy(dtype=object)
    noi["order_id"] = np.char.add(
        "ORD-", (np.arange(n_noi) + 200001).astype(str))  # keep unique
    parts.append(noi)

    # Single assembly pass: concatenate the arrays (C-level memcpy), shuffle
    # once with a numpy permutation, then build the one and only DataFrame.
    total = n_base + n_dup + n_nul + n_inv + n_noi
    perm = rng.permutation(total)
    raw = pd.DataFrame(
        {c: np.concatenate([p[c] for p in parts])[perm] for c in COLS})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(args.out, index=False)
    print(f"Wrote {len(raw):,} rows -> {args.out}")
    print(f"  base={n_base:,} dirty={n_dup + n_nul + n_inv + n_noi:,} "
          f"(dup={n_dup}, nulls={n_nul}, invalid={n_inv}, case-noise={n_noi})")
    assert len(raw) == total


if __name__ == "__main__":
    main()
