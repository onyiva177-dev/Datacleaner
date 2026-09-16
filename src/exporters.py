"""
Export layer.

IMPORTANT AND WORTH BEING ACCURATE ABOUT IN YOUR WRITE-UP:

A .pbix file is a proprietary, undocumented container. There is no supported
library that generates one from scratch, and claiming your app "exports a real
Power BI file" is the kind of claim that falls apart in live Q&A.

What this module does instead is the approach real data teams actually use:
  - export the cleaned data as CSV and Parquet (both Power BI import formats)
  - export a schema/measures document describing the intended model
  - Power BI connects to those in two clicks: Get Data > Text/CSV or Parquet

Say it that way in your demo. "Power BI ready export with a documented model"
is accurate, sounds professional, and you can defend every word of it.
"""
from __future__ import annotations

import json
import os

import pandas as pd


def export_cleaned_csv(df: pd.DataFrame, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def export_parquet(df: pd.DataFrame, output_path: str) -> str:
    """
    Parquet is the better Power BI source for anything large: columnar,
    compressed, and it preserves data types, so Power BI does not re-guess
    them the way it does with CSV.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_parquet(output_path, index=False)
    return output_path


def _suggest_measures(df: pd.DataFrame) -> list[dict]:
    """Suggest DAX measures based on the columns actually present."""
    measures = []
    numeric = list(df.select_dtypes(include="number").columns)
    dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]

    for col in numeric[:6]:
        safe = str(col).replace(" ", "")
        measures.append({"name": f"Total {col}", "dax": f"Total{safe} = SUM('data'[{col}])"})
        measures.append({"name": f"Average {col}", "dax": f"Avg{safe} = AVERAGE('data'[{col}])"})

    measures.append({"name": "Row Count", "dax": "RowCount = COUNTROWS('data')"})

    if dates and numeric:
        d, n = dates[0], numeric[0]
        safe = str(n).replace(" ", "")
        measures.append(
            {
                "name": f"{n} MTD",
                "dax": f"{safe}MTD = TOTALMTD(SUM('data'[{n}]), 'data'[{d}])",
            }
        )
    return measures


def export_powerbi_package(df: pd.DataFrame, output_dir: str, dataset_name: str) -> dict:
    """
    Writes everything a Power BI user needs:
      <name>.csv        - the cleaned data
      <name>.parquet    - same data, typed and compressed
      <name>_model.md   - how to connect, table schema, suggested measures
    """
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, f"{dataset_name}.csv")
    parquet_path = os.path.join(output_dir, f"{dataset_name}.parquet")
    doc_path = os.path.join(output_dir, f"{dataset_name}_model.md")

    df.to_csv(csv_path, index=False)
    try:
        df.to_parquet(parquet_path, index=False)
    except (ImportError, ValueError) as exc:
        print(f"[export] Parquet export skipped: {exc}")
        parquet_path = None

    schema_rows = []
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            pbi_type = "Decimal Number" if s.dtype.kind == "f" else "Whole Number"
        elif pd.api.types.is_datetime64_any_dtype(s):
            pbi_type = "Date/Time"
        elif pd.api.types.is_bool_dtype(s):
            pbi_type = "True/False"
        else:
            pbi_type = "Text"
        schema_rows.append(
            {"column": str(col), "pandas_dtype": str(s.dtype), "power_bi_type": pbi_type}
        )

    measures = _suggest_measures(df)

    lines = [
        f"# {dataset_name} - Power BI Model Guide",
        "",
        "Generated automatically from the cleaned dataset.",
        "",
        "## How to connect",
        "",
        "1. Open Power BI Desktop",
        f"2. Get Data > {'Parquet' if parquet_path else 'Text/CSV'}",
        f"3. Select `{os.path.basename(parquet_path or csv_path)}`",
        "4. Load, then add the measures below under Modeling > New Measure",
        "",
        "## Table schema",
        "",
        "| Column | Type in data | Power BI type |",
        "| --- | --- | --- |",
    ]
    for row in schema_rows:
        lines.append(f"| {row['column']} | {row['pandas_dtype']} | {row['power_bi_type']} |")

    lines += ["", "## Suggested measures (DAX)", ""]
    for m in measures:
        lines.append(f"**{m['name']}**")
        lines.append("")
        lines.append("```")
        lines.append(m["dax"])
        lines.append("```")
        lines.append("")

    with open(doc_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return {
        "csv": csv_path,
        "parquet": parquet_path,
        "model_doc": doc_path,
        "schema": schema_rows,
        "measures": measures,
    }


def export_analysis_json(analysis: dict, output_path: str) -> str:
    """The dashboard payload, also useful as a raw download for users."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=2, default=str)
    return output_path
