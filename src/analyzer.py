"""
Standard data science pass. Runs on BOTH paths - a file that arrived clean and
a file that was just cleaned go through exactly the same analysis here.

Output is dashboard-ready JSON: the frontend renders these structures directly
without recomputing anything.
"""
from __future__ import annotations

import pandas as pd


def _summary_stats(df: pd.DataFrame) -> list[dict]:
    rows = []
    for col in df.columns:
        s = df[col]
        entry = {
            "column": str(col),
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            entry.update(
                {
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "mean": round(float(s.mean()), 4),
                    "median": float(s.median()),
                    "std": round(float(s.std()), 4) if len(s) > 1 else 0.0,
                }
            )
        rows.append(entry)
    return rows


def _correlations(df: pd.DataFrame) -> list[dict]:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(numeric_only=True)
    pairs = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            value = corr.loc[a, b]
            if pd.notna(value):
                pairs.append({"x": str(a), "y": str(b), "correlation": round(float(value), 4)})
    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
    return pairs[:20]


def _categorical_breakdowns(df: pd.DataFrame, max_cols: int = 6, top_n: int = 12) -> list[dict]:
    """Value counts for low-cardinality text columns - these drive the bar/pie charts."""
    out = []
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        nunique = s.nunique(dropna=True)
        if nunique == 0 or nunique > 50:
            continue
        counts = s.value_counts(dropna=True).head(top_n)
        out.append(
            {
                "column": str(col),
                "data": [{"label": str(k), "value": int(v)} for k, v in counts.items()],
            }
        )
        if len(out) >= max_cols:
            break
    return out


def _numeric_distributions(df: pd.DataFrame, max_cols: int = 6, bins: int = 20) -> list[dict]:
    """Histogram buckets - these drive the distribution charts."""
    out = []
    for col in df.select_dtypes(include="number").columns[:max_cols]:
        s = df[col].dropna()
        if len(s) < 2 or s.nunique() < 2:
            continue
        counts, edges = pd.cut(s, bins=min(bins, s.nunique()), retbins=True)
        vc = counts.value_counts().sort_index()
        out.append(
            {
                "column": str(col),
                "data": [
                    {"label": f"{interval.left:.2f} - {interval.right:.2f}", "value": int(count)}
                    for interval, count in vc.items()
                ],
            }
        )
    return out


def _time_series(df: pd.DataFrame, max_series: int = 3) -> list[dict]:
    """
    If there is a date column and numeric columns, produce a daily series.
    This is what makes the dashboard look like a real BI tool rather than
    a pile of bar charts.
    """
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    numeric_cols = list(df.select_dtypes(include="number").columns)
    if not date_cols or not numeric_cols:
        return []

    date_col = date_cols[0]
    out = []
    for num_col in numeric_cols[:max_series]:
        grouped = (
            df.dropna(subset=[date_col])
            .groupby(df[date_col].dt.date)[num_col]
            .sum()
            .sort_index()
        )
        out.append(
            {
                "date_column": str(date_col),
                "value_column": str(num_col),
                "data": [{"label": str(d), "value": float(v)} for d, v in grouped.items()],
            }
        )
    return out


def analyze(df: pd.DataFrame) -> dict:
    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "summary_stats": _summary_stats(df),
        "correlations": _correlations(df),
        "categorical": _categorical_breakdowns(df),
        "distributions": _numeric_distributions(df),
        "time_series": _time_series(df),
    }
