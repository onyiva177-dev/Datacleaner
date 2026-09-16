"""
Run the whole pipeline from the command line, no Airflow, no database.
This is your fastest feedback loop while building - use it constantly.

Usage:
    python scripts/run_local.py data/samples/sales_messy.csv
    python scripts/run_local.py data/samples/sales_clean.csv --out data/output/clean.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the cleaning pipeline locally.")
    parser.add_argument("input", help="Path to the input CSV")
    parser.add_argument("--out", default=None, help="Path for the cleaned CSV")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    args = parser.parse_args()

    out = args.out or os.path.join(
        "data", "output", os.path.basename(args.input).replace(".csv", "_cleaned.csv")
    )

    print("=" * 70)
    result = pipeline.run_full_pipeline(args.input, out, dataset_id=None)
    print("=" * 70)

    print("\nCLEANING LOG")
    print("-" * 70)
    for entry in result["log"]:
        marker = {"applied": "[OK]", "rejected": "[REJECTED]", "failed": "[FAILED]"}.get(
            entry["status"], "[?]"
        )
        col = entry["column"] or "<table>"
        print(f"{marker:11} {col:20} {entry['action']:20} {entry['reason']}")
        if entry["detail"]:
            print(f"{'':11} -> {entry['detail']}")

    print("\nBEFORE / AFTER")
    print("-" * 70)
    p = result["profile"]
    a = result["analysis"]
    print(f"Rows:    {p['row_count']:>8}  ->  {a['row_count']:>8}")
    print(f"Columns: {p['column_count']:>8}  ->  {a['column_count']:>8}")
    print(f"Nulls:   {p['total_nulls']:>8}  ->  (see cleaned file)")
    print(f"Plan source: {result['plan']['source']}")

    if args.json:
        print("\nFULL RESULT JSON")
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
