#!/usr/bin/env python3
"""
Generate the raw e-commerce orders dataset for the
"E-Commerce Sales Performance Dashboard" project.

Output: data/raw/ecommerce_orders.csv  (~58,000 rows)

The raw file is INTENTIONALLY dirty (duplicates, nulls, invalid values,
case/whitespace inconsistencies ~= 7% of rows) so the SQL/Python cleaning
step (sql/cleaning.sql, data/clean_data.py) has real work to do.

Reproducible: fixed seed (SEED = 42).
"""
import calendar
import numpy as np
import pandas as pd
from pathlib import Path

SEED = 42
N_BASE = 54_000        # clean base orders
N_DIRTY = 4_000        # intentionally dirty rows appended on top
OUT = Path(__file__).resolve().parent / "raw" / "ecommerce_orders.csv"

rng = np.random.default_rng(SEED)

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

# ------------------------------------------------------------- seasonality
# Monthly demand multipliers: Diwali (Oct-Nov) + year-end (Dec) spikes.
MONTH_W = {1: 0.90, 2: 0.75, 3: 0.85, 4: 0.90, 5: 0.95, 6: 0.80,
           7: 0.80, 8: 0.95, 9: 1.00, 10: 1.35, 11: 1.30, 12: 1.25}
PERIOD_MONTHS = [(y, m) for y in (2023, 2024) for m in range(1, 13)] + \
                [(2025, m) for m in range(1, 10)]          # 2023-01 .. 2025-09
PERIOD_W = np.array([MONTH_W[m] for _, m in PERIOD_MONTHS], dtype=float)
PERIOD_W /= PERIOD_W.sum()

AGE_GROUPS = ["18-25", "26-35", "36-45", "46-60"]
AGE_W = [0.28, 0.38, 0.22, 0.12]
GENDERS, GENDER_W = ["Male", "Female"], [0.54, 0.46]
PAYMENTS = ["UPI", "Cash on Delivery", "Credit Card", "Debit Card", "Net Banking", "Wallet"]
PAY_W = [0.38, 0.22, 0.15, 0.12, 0.08, 0.05]
STATUSES, STATUS_W = ["Delivered", "Cancelled", "Returned"], [0.90, 0.06, 0.04]


def sample_dates(n):
    idx = rng.choice(len(PERIOD_MONTHS), size=n, p=PERIOD_W)
    out = []
    for i in idx:
        y, m = PERIOD_MONTHS[i]
        d = int(rng.integers(1, calendar.monthrange(y, m)[1] + 1))
        out.append(f"{y:04d}-{m:02d}-{d:02d}")
    return np.array(out)


def main():
    # ---- customer master: 16k customers with home geography + demographics
    n_cust = 16_000
    cust_regions = rng.choice(list(REGION_MAP), size=n_cust,
                              p=[REGION_W[r] for r in REGION_MAP])
    cust_state, cust_city = [], []
    for r in cust_regions:
        s = rng.choice(list(REGION_MAP[r].keys()))
        cust_state.append(s)
        cust_city.append(str(rng.choice(REGION_MAP[r][s])))
    customers = pd.DataFrame({
        "customer_id": [f"CUST-{i:05d}" for i in range(1, n_cust + 1)],
        "region": cust_regions,
        "state": cust_state,
        "city": cust_city,
        "customer_age_group": rng.choice(AGE_GROUPS, size=n_cust, p=AGE_W),
        "customer_gender": rng.choice(GENDERS, size=n_cust, p=GENDER_W),
    })
    # power-law-ish repeat purchase propensity (a few customers buy a lot)
    propensity = rng.exponential(scale=1.0, size=n_cust)
    propensity /= propensity.sum()

    # ---- base orders
    cust_idx = rng.choice(n_cust, size=N_BASE, p=propensity)
    base = customers.iloc[cust_idx].reset_index(drop=True)

    cats = rng.choice(CATEGORIES, size=N_BASE, p=CAT_W)
    prod_names, base_prices = [], []
    for c in cats:
        names = list(PRODUCTS[c].keys())
        nm = str(rng.choice(names))
        prod_names.append(nm)
        base_prices.append(PRODUCTS[c][nm])
    base_prices = np.array(base_prices, dtype=float)

    order_date = sample_dates(N_BASE)
    festival = np.array([d[5:7] in ("10", "11", "12") for d in order_date])

    qty = rng.choice([1, 2, 3, 4, 5], size=N_BASE, p=[0.55, 0.25, 0.12, 0.05, 0.03])
    unit_price = np.round(base_prices * rng.uniform(0.85, 1.15, N_BASE)).astype(int)
    disc = rng.beta(2, 5, N_BASE) * 40 + np.where(festival, 8, 0)
    disc = np.clip(disc, 0, 45).round(1)
    disc[rng.random(N_BASE) < 0.20] = 0.0  # no-discount orders

    df = pd.DataFrame({
        "order_id": [f"ORD-{100001 + i}" for i in range(N_BASE)],
        "order_date": order_date,
        "region": base["region"].values,
        "state": base["state"].values,
        "city": base["city"].values,
        "product_category": cats,
        "product_name": prod_names,
        "quantity": qty,
        "unit_price": unit_price,
        "discount_pct": disc,
        "customer_id": base["customer_id"].values,
        "customer_age_group": base["customer_age_group"].values,
        "customer_gender": base["customer_gender"].values,
        "payment_method": rng.choice(PAYMENTS, size=N_BASE, p=PAY_W),
        "order_status": rng.choice(STATUSES, size=N_BASE, p=STATUS_W),
    })

    # ---- dirty rows (~7%): duplicates, nulls, invalids, case/whitespace noise
    dirty_parts = []
    # 1) exact duplicates
    dup = df.sample(1500, random_state=SEED).copy()
    dirty_parts.append(dup)
    # 2) nulls in key fields (discount nulls are fillable -> kept by cleaning)
    nul = df.sample(1200, random_state=SEED + 1).copy()
    nul_fields = rng.choice(["order_date", "quantity", "unit_price", "region",
                             "customer_id", "discount_pct"], size=len(nul))
    for i, f in enumerate(nul_fields):
        nul.iloc[i, nul.columns.get_loc(f)] = np.nan
    dirty_parts.append(nul)
    # 3) invalid values
    inv = df.sample(800, random_state=SEED + 2).copy()
    inv_kind = rng.choice(["neg_qty", "zero_price", "huge_discount",
                           "bad_date", "bad_region"], size=len(inv))
    for i, k in enumerate(inv_kind):
        r = inv.index[i]
        if k == "neg_qty":
            inv.loc[r, "quantity"] = -int(rng.integers(1, 4))
        elif k == "zero_price":
            inv.loc[r, "unit_price"] = 0
        elif k == "huge_discount":
            inv.loc[r, "discount_pct"] = 150.0
        elif k == "bad_date":
            inv.loc[r, "order_date"] = "2024-13-45"
        else:
            inv.loc[r, "region"] = str(rng.choice(["N/A", "unknown", ""]))
    dirty_parts.append(inv)
    # 4) case/whitespace noise (valid rows, standardised by cleaning)
    noi = df.sample(500, random_state=SEED + 3).copy()
    noi["region"] = noi["region"].str.lower().str.pad(8, side="both")
    noi["product_category"] = noi["product_category"].str.upper()
    noi["order_id"] = [f"ORD-{200001 + i}" for i in range(len(noi))]  # keep unique
    dirty_parts.append(noi)

    raw = pd.concat([df] + dirty_parts, ignore_index=True)
    raw = raw.sample(frac=1.0, random_state=SEED).reset_index(drop=True)  # shuffle

    OUT.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(OUT, index=False)
    print(f"Wrote {len(raw):,} rows -> {OUT}")
    print(f"  base={N_BASE:,} dirty={N_DIRTY:,} "
          f"(dup=1500, nulls=1200, invalid=800, case-noise=500)")
    assert len(raw) >= 50_000, "raw row count below 50k!"


if __name__ == "__main__":
    main()
