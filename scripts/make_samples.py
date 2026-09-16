"""
Generates two sample CSVs so you can test both pipeline paths immediately:
  data/samples/sales_clean.csv  - should skip the AI entirely
  data/samples/sales_messy.csv  - nulls, duplicates, mixed dates, outliers, whitespace

Run:  python scripts/make_samples.py
"""
from __future__ import annotations

import os
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "samples")

PRODUCTS = ["Laptop", "Phone", "Headphones", "Monitor", "Keyboard", "Tablet"]
CATEGORIES = {"Laptop": "Computers", "Monitor": "Computers", "Keyboard": "Accessories",
              "Phone": "Mobile", "Tablet": "Mobile", "Headphones": "Accessories"}
REGIONS = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"]
PAYMENTS = ["Card", "Mobile Money", "Cash", "Bank Transfer"]


def build_base(n: int = 3000) -> pd.DataFrame:
    start = date(2025, 1, 1)
    rows = []
    for i in range(n):
        product = random.choice(PRODUCTS)
        quantity = random.randint(1, 5)
        unit_price = round(random.uniform(500, 90000), 2)
        rows.append({
            "transaction_id": f"TXN{100000 + i}",
            "date": (start + timedelta(days=random.randint(0, 364))).isoformat(),
            "product": product,
            "category": CATEGORIES[product],
            "quantity": quantity,
            "unit_price": unit_price,
            "total": round(quantity * unit_price, 2),
            "customer_id": f"CUST{random.randint(1000, 1400)}",
            "region": random.choice(REGIONS),
            "payment_method": random.choice(PAYMENTS),
        })
    return pd.DataFrame(rows)


def make_messy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Nulls in a numeric column
    null_idx = df.sample(frac=0.08).index
    df.loc[null_idx, "unit_price"] = np.nan

    # 2. Nulls in a categorical column
    df.loc[df.sample(frac=0.05).index, "region"] = np.nan

    # 3. Mixed date formats
    mixed_idx = df.sample(frac=0.30).index
    df.loc[mixed_idx, "date"] = pd.to_datetime(
        df.loc[mixed_idx, "date"]
    ).dt.strftime("%d/%m/%Y")

    # 4. Whitespace and inconsistent casing
    ws_idx = df.sample(frac=0.15).index
    df.loc[ws_idx, "product"] = "  " + df.loc[ws_idx, "product"].astype(str) + " "
    case_idx = df.sample(frac=0.15).index
    df.loc[case_idx, "payment_method"] = df.loc[case_idx, "payment_method"].str.upper()

    # 5. Outliers
    out_idx = df.sample(n=25).index
    df.loc[out_idx, "quantity"] = np.random.randint(400, 900, size=len(out_idx))

    # 6. Exact duplicate rows
    duplicates = df.sample(n=120)
    df = pd.concat([df, duplicates], ignore_index=True)

    return df.sample(frac=1, random_state=7).reset_index(drop=True)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base = build_base()

    clean_path = os.path.join(OUT_DIR, "sales_clean.csv")
    messy_path = os.path.join(OUT_DIR, "sales_messy.csv")

    base.to_csv(clean_path, index=False)
    make_messy(base).to_csv(messy_path, index=False)

    print(f"Wrote {clean_path} ({len(base)} rows)")
    messy = pd.read_csv(messy_path)
    print(f"Wrote {messy_path} ({len(messy)} rows, "
          f"{int(messy.isna().sum().sum())} nulls, "
          f"{int(messy.duplicated().sum())} duplicate rows)")


if __name__ == "__main__":
    main()
