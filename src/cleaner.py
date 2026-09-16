"""
Executes a validated cleaning plan and records exactly what changed.

Every action returns a log entry with real before/after numbers measured from
the dataframe - not the numbers the AI predicted. If the AI said "12 nulls" and
only 9 were actually filled, the log shows 9.
"""
from __future__ import annotations

import pandas as pd


def _is_text(series) -> bool:
    """
    True for string-like columns. Checking `dtype == object` breaks on newer
    pandas where string columns get a dedicated `str` dtype, so we check by
    exclusion instead.
    """
    return not (
        pd.api.types.is_numeric_dtype(series)
        or pd.api.types.is_datetime64_any_dtype(series)
        or pd.api.types.is_bool_dtype(series)
    )


def _fill_null_median(df, col, params):
    before = int(df[col].isna().sum())
    value = df[col].median()
    df[col] = df[col].fillna(value)
    return df, {"filled": before, "value_used": float(value) if pd.notna(value) else None}


def _fill_null_mean(df, col, params):
    before = int(df[col].isna().sum())
    value = df[col].mean()
    df[col] = df[col].fillna(value)
    return df, {"filled": before, "value_used": float(value) if pd.notna(value) else None}


def _fill_null_mode(df, col, params):
    before = int(df[col].isna().sum())
    modes = df[col].mode(dropna=True)
    value = modes.iloc[0] if len(modes) else None
    if value is not None:
        df[col] = df[col].fillna(value)
    return df, {"filled": before if value is not None else 0, "value_used": str(value)}


def _fill_null_constant(df, col, params):
    before = int(df[col].isna().sum())
    value = params.get("value", "UNKNOWN")
    df[col] = df[col].fillna(value)
    return df, {"filled": before, "value_used": str(value)}


def _drop_null_rows(df, col, params):
    before = len(df)
    df = df[df[col].notna()]
    return df, {"rows_dropped": before - len(df)}


def _drop_duplicates(df, col, params):
    before = len(df)
    df = df.drop_duplicates()
    return df, {"rows_dropped": before - len(df)}


def _parse_dates(df, col, params):
    before_valid = int(pd.to_datetime(df[col], errors="coerce", format="mixed").notna().sum())
    df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    after_valid = int(df[col].notna().sum())
    return df, {"parsed": after_valid, "unparseable": len(df) - after_valid}


def _strip_whitespace(df, col, params):
    if _is_text(df[col]):
        changed = int((df[col].astype(str) != df[col].astype(str).str.strip()).sum())
        df[col] = df[col].astype(str).str.strip()
        return df, {"values_trimmed": changed}
    return df, {"values_trimmed": 0}


def _standardize_case(df, col, params):
    mode = params.get("case", "lower")
    if _is_text(df[col]):
        if mode == "upper":
            df[col] = df[col].astype(str).str.upper()
        elif mode == "title":
            df[col] = df[col].astype(str).str.title()
        else:
            df[col] = df[col].astype(str).str.lower()
        return df, {"case_applied": mode}
    return df, {"case_applied": "skipped_non_text"}


def _cast_numeric(df, col, params):
    before_valid = int(pd.to_numeric(df[col], errors="coerce").notna().sum())
    df[col] = pd.to_numeric(df[col], errors="coerce")
    return df, {"converted": before_valid, "failed": len(df) - before_valid}


def _clip_outliers(df, col, params):
    q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    clipped = int(((df[col] < lower) | (df[col] > upper)).sum())
    df[col] = df[col].clip(lower, upper)
    return df, {"values_clipped": clipped, "lower": float(lower), "upper": float(upper)}


def _drop_column(df, col, params):
    df = df.drop(columns=[col])
    return df, {"column_dropped": col}


ACTION_MAP = {
    "fill_null_median": _fill_null_median,
    "fill_null_mean": _fill_null_mean,
    "fill_null_mode": _fill_null_mode,
    "fill_null_constant": _fill_null_constant,
    "drop_null_rows": _drop_null_rows,
    "drop_duplicates": _drop_duplicates,
    "parse_dates": _parse_dates,
    "strip_whitespace": _strip_whitespace,
    "standardize_case": _standardize_case,
    "cast_numeric": _cast_numeric,
    "clip_outliers": _clip_outliers,
    "drop_column": _drop_column,
}


def apply_plan(df: pd.DataFrame, validated: dict) -> tuple[pd.DataFrame, list]:
    """
    Run every accepted step. Returns the cleaned dataframe and the audit log.

    A step that raises is logged as failed and the pipeline continues - one bad
    step should not lose the whole run.
    """
    df = df.copy()
    log = []

    for step in validated["accepted"]:
        action = step["action"]
        col = step.get("column")
        params = step.get("params") or {}
        handler = ACTION_MAP[action]

        rows_before, cols_before = df.shape
        try:
            df, detail = handler(df, col, params)
            status = "applied"
            error = None
        except Exception as exc:  # noqa: BLE001 - deliberate: log and continue
            detail, status, error = {}, "failed", f"{type(exc).__name__}: {exc}"

        log.append(
            {
                "column": col,
                "action": action,
                "reason": step.get("reason", ""),
                "status": status,
                "error": error,
                "rows_before": rows_before,
                "rows_after": int(df.shape[0]),
                "columns_before": cols_before,
                "columns_after": int(df.shape[1]),
                "detail": detail,
            }
        )

    for rejected in validated["rejected"]:
        log.append(
            {
                "column": (rejected["step"] or {}).get("column")
                if isinstance(rejected.get("step"), dict)
                else None,
                "action": (rejected["step"] or {}).get("action")
                if isinstance(rejected.get("step"), dict)
                else "unknown",
                "reason": rejected["reason"],
                "status": "rejected",
                "error": None,
                "rows_before": None,
                "rows_after": None,
                "columns_before": None,
                "columns_after": None,
                "detail": {},
            }
        )

    return df, log
