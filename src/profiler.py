"""
Data profiling. Runs BEFORE any cleaning and before the AI is called.

Everything here is deterministic - no AI, no guessing. The numbers this module
produces are the ground truth that the AI's cleaning plan gets checked against
in validator.py. If the AI claims something this module did not measure, the
plan is rejected.
"""
from __future__ import annotations

import pandas as pd


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series)


def _date_parse_ratio(series: pd.Series) -> float:
    """Fraction of a sample of non-null values that parse as dates."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return 0.0
    sample = non_null.astype(str).head(200)
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return 0.0
    return float(parsed.notna().mean())


def _outlier_count_iqr(series: pd.Series) -> int:
    """Count outliers using the IQR rule. Numeric columns only."""
    clean = series.dropna()
    if len(clean) < 4:
        return 0
    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((clean < lower) | (clean > upper)).sum())


def _whitespace_count(series: pd.Series) -> int:
    """Count text values with leading or trailing whitespace."""
    if _is_numeric(series) or pd.api.types.is_datetime64_any_dtype(series):
        return 0
    non_null = series.dropna().astype(str)
    if len(non_null) == 0:
        return 0
    return int((non_null != non_null.str.strip()).sum())


def _case_inconsistent(series: pd.Series) -> bool:
    """
    True when the same value appears in different cases, e.g. 'Card' and 'CARD'.
    Detected by comparing unique counts before and after lowercasing.
    """
    if _is_numeric(series) or pd.api.types.is_datetime64_any_dtype(series):
        return False
    non_null = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return False
    return int(non_null.nunique()) > int(non_null.str.lower().nunique())


def profile_column(series: pd.Series) -> dict:
    total = len(series)
    null_count = int(series.isna().sum())

    info = {
        "dtype": str(series.dtype),
        "total_rows": total,
        "null_count": null_count,
        "null_pct": round(null_count / total * 100, 2) if total else 0.0,
        "unique_count": int(series.nunique(dropna=True)),
        "is_numeric": _is_numeric(series),
        "date_parse_ratio": round(_date_parse_ratio(series), 2),
        "outlier_count": _outlier_count_iqr(series) if _is_numeric(series) else 0,
        "whitespace_count": _whitespace_count(series),
        "case_inconsistent": _case_inconsistent(series),
        "sample_values": [str(v) for v in series.dropna().head(5).tolist()],
    }

    if _is_numeric(series) and series.notna().any():
        info.update(
            {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": round(float(series.mean()), 4),
                "median": float(series.median()),
                "std": round(float(series.std()), 4) if total > 1 else 0.0,
            }
        )

    return info


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Produce the full profile report for a dataframe."""
    duplicate_rows = int(df.duplicated().sum())
    columns = {str(col): profile_column(df[col]) for col in df.columns}

    total_cells = int(df.shape[0] * df.shape[1])
    total_nulls = int(df.isna().sum().sum())

    issues = []
    for col, info in columns.items():
        if info["null_count"] > 0:
            issues.append(f"{col}: {info['null_count']} nulls ({info['null_pct']}%)")
        if info["outlier_count"] > 0:
            issues.append(f"{col}: {info['outlier_count']} outliers (IQR rule)")
        if not info["is_numeric"] and 0.5 < info["date_parse_ratio"] < 1.0:
            issues.append(
                f"{col}: inconsistent date formats ({info['date_parse_ratio']} parse rate)"
            )
        if (
            not info["is_numeric"]
            and info["date_parse_ratio"] >= 0.9
            and not info["dtype"].startswith("datetime")
        ):
            issues.append(f"{col}: stored as text but contains dates - should be typed as date")
        if info["whitespace_count"] > 0:
            issues.append(f"{col}: {info['whitespace_count']} values with stray whitespace")
        if info["case_inconsistent"]:
            issues.append(f"{col}: inconsistent capitalisation of the same values")
    if duplicate_rows:
        issues.append(f"{duplicate_rows} exact duplicate rows")

    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "duplicate_rows": duplicate_rows,
        "total_cells": total_cells,
        "total_nulls": total_nulls,
        "null_pct_overall": round(total_nulls / total_cells * 100, 2) if total_cells else 0.0,
        "columns": columns,
        "issues": issues,
        "needs_cleaning": bool(issues),
    }
