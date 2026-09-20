"""
The pipeline steps, written as plain functions so they can be:
  - called directly from the CLI (scripts/run_local.py) for fast testing
  - wrapped by Airflow tasks (dags/csv_cleaning_dag.py) for orchestration

Keeping the logic OUT of the DAG file is deliberate: you can test the whole
pipeline without starting Airflow, which saves a lot of time on build day.
"""
from __future__ import annotations

import os

import pandas as pd

from . import ai_planner, analyzer, cleaner, db, profiler, validator


def read_csv(path: str) -> pd.DataFrame:
    """
    Read defensively. Real uploaded files are messy: odd encodings, stray
    delimiters, blank lines. skip_blank_lines and the encoding fallback handle
    the two failures that actually show up in practice.
    """
    try:
        df = pd.read_csv(path, skip_blank_lines=True)
    except UnicodeDecodeError:
        df = pd.read_csv(path, skip_blank_lines=True, encoding="latin-1")
    except pd.errors.ParserError as exc:
        # Fail loudly and readably. In Airflow this message lands on the task
        # log and on the dataset row, so the user sees why their file was
        # rejected instead of a raw pandas traceback.
        raise ValueError(
            f"Could not parse '{os.path.basename(path)}' as CSV. "
            f"The file appears malformed (unclosed quote or inconsistent "
            f"column count). Original error: {exc}"
        ) from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"'{os.path.basename(path)}' is empty.") from exc

    if df.empty:
        raise ValueError(f"'{os.path.basename(path)}' contains no data rows.")
    return df


def step_profile(input_path: str, dataset_id: int | None = None) -> dict:
    if dataset_id:
        db.set_stage(dataset_id, "profiling")
    df = read_csv(input_path)
    profile = profiler.profile_dataframe(df)
    if dataset_id:
        db.save_profile(dataset_id, profile)
    print(f"[profile] {profile['row_count']} rows, {profile['column_count']} cols, "
          f"{len(profile['issues'])} issues found")
    return profile


def step_plan(profile: dict, dataset_id: int | None = None) -> dict:
    """
    Branch point: clean files skip the AI entirely. This is a cost decision as
    much as a design one - no point paying for an API call on a clean file.
    """
    if dataset_id:
        db.set_stage(dataset_id, "planning")

    if not profile["needs_cleaning"]:
        print("[plan] File is already clean. Skipping AI planner.")
        return {"steps": [], "source": "skipped_clean"}

    plan = ai_planner.generate_plan(profile)
    print(f"[plan] {len(plan['steps'])} steps proposed (source: {plan['source']})")
    return plan


def step_validate(plan: dict, profile: dict, dataset_id: int | None = None) -> dict:
    if dataset_id:
        db.set_stage(dataset_id, "validating")
    validated = validator.validate_plan(plan, profile)
    print(f"[validate] {len(validated['accepted'])} accepted, "
          f"{len(validated['rejected'])} rejected")
    for r in validated["rejected"]:
        print(f"[validate] REJECTED: {r['reason']}")
    return validated


def step_clean(input_path: str, validated: dict, output_path: str,
               dataset_id: int | None = None) -> tuple[pd.DataFrame, list]:
    if dataset_id:
        db.set_stage(dataset_id, "cleaning")
    df = read_csv(input_path)
    cleaned, log = cleaner.apply_plan(df, validated)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cleaned.to_csv(output_path, index=False)

    if dataset_id:
        db.save_cleaning_log(dataset_id, log, validated.get("source", "unknown"))

    applied = sum(1 for e in log if e["status"] == "applied")
    print(f"[clean] {applied} steps applied. Output: {output_path} "
          f"({cleaned.shape[0]} rows, {cleaned.shape[1]} cols)")
    return cleaned, log


def _reinfer_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    CSV has no type system, so dates parsed during cleaning come back as text
    when the cleaned file is re-read. Re-infer them here so the analyzer can
    build time series. Only converts columns where nearly every value parses.
    """
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        sample = df[col].dropna().astype(str).head(200)
        if len(sample) == 0:
            continue
        try:
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        except (ValueError, TypeError):
            continue
        if parsed.notna().mean() >= 0.95:
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    return df


def step_analyze(cleaned_path: str, dataset_id: int | None = None) -> dict:
    if dataset_id:
        db.set_stage(dataset_id, "analyzing")
    df = _reinfer_dates(read_csv(cleaned_path))
    results = analyzer.analyze(df)
    if dataset_id:
        db.save_analysis(dataset_id, results)
    print(f"[analyze] {len(results['summary_stats'])} columns summarised, "
          f"{len(results['categorical'])} categorical breakdowns, "
          f"{len(results['time_series'])} time series")
    return results


def run_full_pipeline(input_path: str, output_path: str,
                      dataset_id: int | None = None) -> dict:
    """End-to-end run. Used by the CLI and by tests."""
    profile = step_profile(input_path, dataset_id)
    plan = step_plan(profile, dataset_id)
    validated = step_validate(plan, profile, dataset_id)
    validated["source"] = plan.get("source", "unknown")
    cleaned, log = step_clean(input_path, validated, output_path, dataset_id)
    results = step_analyze(output_path, dataset_id)

    if dataset_id:
        db.set_stage(dataset_id, "complete")
        db.finalize_dataset(dataset_id, cleaned.shape[0], cleaned.shape[1], output_path)

    return {
        "profile": profile,
        "plan": plan,
        "validated": validated,
        "log": log,
        "analysis": results,
    }
