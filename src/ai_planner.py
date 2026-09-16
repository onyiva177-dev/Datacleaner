"""
The AI layer. This is the ONLY place an AI model is called.

Design decision worth defending in a demo: the AI never sees the raw data and
never executes anything. It receives the deterministic profile report from
profiler.py and returns a structured cleaning PLAN as JSON. The plan is then
checked against the real profile by validator.py before a single row is touched.

This means:
  - no user data is sent to a third party, only column statistics
  - a hallucinated column name or invented null count gets caught, not applied
  - if the AI is unavailable, the pipeline falls back to deterministic rules
"""
from __future__ import annotations

import json
import os
import re

import requests

ALLOWED_ACTIONS = {
    "drop_duplicates",
    "fill_null_median",
    "fill_null_mean",
    "fill_null_mode",
    "fill_null_constant",
    "drop_null_rows",
    "parse_dates",
    "strip_whitespace",
    "standardize_case",
    "cast_numeric",
    "clip_outliers",
    "drop_column",
}

SYSTEM_PROMPT = """You are a data cleaning planner. You will receive a JSON profile
report of a tabular dataset. You must respond with ONLY a JSON object, no markdown
fences, no commentary.

Schema:
{
  "steps": [
    {"column": "<column name or null for whole-table actions>",
     "action": "<one of the allowed actions>",
     "params": {},
     "reason": "<one short sentence citing the specific number from the profile>"}
  ]
}

Allowed actions: drop_duplicates, fill_null_median, fill_null_mean, fill_null_mode,
fill_null_constant, drop_null_rows, parse_dates, strip_whitespace, standardize_case,
cast_numeric, clip_outliers, drop_column.

Rules:
- Only reference column names that appear in the profile. Never invent one.
- Only cite counts that appear in the profile. Never estimate.
- Only propose a step if the profile shows an actual problem for that column.
- drop_duplicates uses column: null.
- Prefer median over mean for numeric nulls when outliers are present.
- Do not propose drop_column unless null_pct is above 60.
- If the dataset has no issues, return {"steps": []}.
"""


def _strip_fences(text: str) -> str:
    """Models sometimes wrap JSON in markdown fences despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _compact_profile(profile: dict) -> dict:
    """Send only what the planner needs. Keeps the prompt small and cheap."""
    return {
        "row_count": profile["row_count"],
        "duplicate_rows": profile["duplicate_rows"],
        "issues": profile["issues"],
        "columns": {
            col: {
                k: v
                for k, v in info.items()
                if k
                in (
                    "dtype",
                    "null_count",
                    "null_pct",
                    "unique_count",
                    "is_numeric",
                    "date_parse_ratio",
                    "outlier_count",
                    "sample_values",
                )
            }
            for col, info in profile["columns"].items()
        },
    }


def fallback_plan(profile: dict) -> dict:
    """
    Deterministic plan used when the AI is unavailable or returns garbage.
    The pipeline must never hard-fail just because an API call did.
    """
    steps = []
    if profile["duplicate_rows"] > 0:
        steps.append(
            {
                "column": None,
                "action": "drop_duplicates",
                "params": {},
                "reason": f"{profile['duplicate_rows']} exact duplicate rows found.",
            }
        )
    for col, info in profile["columns"].items():
        if info["null_count"] > 0:
            if info["is_numeric"]:
                action = "fill_null_median" if info["outlier_count"] > 0 else "fill_null_mean"
            else:
                action = "fill_null_mode"
            steps.append(
                {
                    "column": col,
                    "action": action,
                    "params": {},
                    "reason": f"{info['null_count']} nulls in {col}.",
                }
            )
        if info.get("whitespace_count", 0) > 0:
            steps.append(
                {
                    "column": col,
                    "action": "strip_whitespace",
                    "params": {},
                    "reason": f"{info['whitespace_count']} values in {col} have stray whitespace.",
                }
            )
        if info.get("case_inconsistent"):
            steps.append(
                {
                    "column": col,
                    "action": "standardize_case",
                    "params": {"case": "title"},
                    "reason": f"Inconsistent capitalisation in {col}.",
                }
            )
        if not info["is_numeric"] and info["date_parse_ratio"] > 0.5:
            steps.append(
                {
                    "column": col,
                    "action": "parse_dates",
                    "params": {},
                    "reason": f"{col} contains dates stored as text "
                    f"(parse ratio {info['date_parse_ratio']}).",
                }
            )
        if info["is_numeric"] and info["outlier_count"] > 0:
            steps.append(
                {
                    "column": col,
                    "action": "clip_outliers",
                    "params": {},
                    "reason": f"{info['outlier_count']} outliers in {col} (IQR rule).",
                }
            )
    return {"steps": steps, "source": "fallback"}


def generate_plan(profile: dict, timeout: int = 45) -> dict:
    """
    Ask the AI for a cleaning plan. Falls back to deterministic rules on any
    failure: no key, network error, bad status, unparseable JSON.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        print("[ai_planner] No GEMINI_API_KEY set, using deterministic fallback plan.")
        return fallback_plan(profile)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(_compact_profile(profile), default=str)}],
            }
        ],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        plan = json.loads(_strip_fences(text))
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"[ai_planner] AI call failed ({type(exc).__name__}: {exc}). Using fallback.")
        return fallback_plan(profile)

    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        print("[ai_planner] AI returned unexpected shape. Using fallback.")
        return fallback_plan(profile)

    plan["source"] = "ai"
    return plan
