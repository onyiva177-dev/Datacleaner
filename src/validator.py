"""
The anti-hallucination gate.

Every step the AI proposes is checked against the deterministic profile before
it is allowed to run. A step is rejected if it:
  - names a column that does not exist
  - uses an action that is not in the allowlist
  - proposes a null-filling step for a column with zero nulls
  - proposes dropping duplicates when there are none
  - proposes clipping outliers on a column with no detected outliers
  - proposes dropping a column that is not mostly empty

Rejected steps are not silently discarded - they are recorded with a reason and
surfaced in the cleaning log and the UI. This is the feature that makes the
project defensible: the AI advises, the pipeline verifies.
"""
from __future__ import annotations

from .ai_planner import ALLOWED_ACTIONS

WHOLE_TABLE_ACTIONS = {"drop_duplicates"}
NULL_FILL_ACTIONS = {
    "fill_null_median",
    "fill_null_mean",
    "fill_null_mode",
    "fill_null_constant",
    "drop_null_rows",
}
NUMERIC_ONLY_ACTIONS = {"fill_null_median", "fill_null_mean", "clip_outliers"}


def validate_plan(plan: dict, profile: dict) -> dict:
    """
    Split the plan into accepted and rejected steps.

    Returns {"accepted": [...], "rejected": [...], "source": "ai"|"fallback"}
    """
    accepted, rejected = [], []
    columns = profile["columns"]

    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            rejected.append({"step": step, "reason": "Step is not an object."})
            continue

        action = step.get("action")
        column = step.get("column")

        if action not in ALLOWED_ACTIONS:
            rejected.append({"step": step, "reason": f"Unknown action '{action}'."})
            continue

        if action in WHOLE_TABLE_ACTIONS:
            if profile["duplicate_rows"] == 0:
                rejected.append(
                    {"step": step, "reason": "No duplicate rows exist in the dataset."}
                )
            else:
                accepted.append(step)
            continue

        if column is None or column not in columns:
            rejected.append(
                {"step": step, "reason": f"Column '{column}' does not exist in the dataset."}
            )
            continue

        info = columns[column]

        if action in NULL_FILL_ACTIONS and info["null_count"] == 0:
            rejected.append(
                {"step": step, "reason": f"Column '{column}' has no nulls to fill."}
            )
            continue

        if action in NUMERIC_ONLY_ACTIONS and not info["is_numeric"]:
            rejected.append(
                {"step": step, "reason": f"Column '{column}' is not numeric."}
            )
            continue

        if action == "clip_outliers" and info["outlier_count"] == 0:
            rejected.append(
                {"step": step, "reason": f"No outliers detected in '{column}'."}
            )
            continue

        if action == "parse_dates" and info["date_parse_ratio"] < 0.5:
            rejected.append(
                {
                    "step": step,
                    "reason": f"'{column}' does not look like a date column "
                    f"(parse ratio {info['date_parse_ratio']}).",
                }
            )
            continue

        if action == "drop_column" and info["null_pct"] <= 60:
            rejected.append(
                {
                    "step": step,
                    "reason": f"'{column}' is only {info['null_pct']}% null - too valuable to drop.",
                }
            )
            continue

        accepted.append(step)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "source": plan.get("source", "unknown"),
    }
