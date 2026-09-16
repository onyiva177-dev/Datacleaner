"""
Airflow DAG: orchestrates one CSV through the full pipeline.

Task graph:

    profile_data
         |
    branch_on_quality  ------------------> skip_ai_planning
         |                                        |
    generate_ai_plan                              |
         |                                        |
    validate_plan                                 |
         |                                        |
         +--------------> clean_data <------------+
                              |
                         analyze_data
                              |
                         finalize

Why these tasks exist (the question you will be asked in a demo):

  profile_data       Deterministic measurement. Produces the ground truth that
                     everything downstream is checked against.
  branch_on_quality  A clean file should not cost an AI API call. BranchPython
                     Operator routes clean files around the AI entirely.
  generate_ai_plan   The only AI call. Sends column statistics, never raw data.
  validate_plan      Rejects hallucinated steps before anything is executed.
  clean_data         Executes only validated steps, logging real before/after
                     numbers.
  analyze_data       Same analysis for both paths, so output is consistent.
  finalize           Marks the dataset complete so the frontend can show it.

Data moves between tasks via XCom (small JSON: profiles, plans, logs). The
actual CSV files move via the shared volume at /opt/airflow/data - XCom is not
for file payloads.

Failure handling: a malformed CSV fails profile_data, the DAG stops, and
nothing corrupt reaches the database. The dataset row is marked 'failed' with
the error, which the UI surfaces. Break it on purpose and screenshot this -
it demos far better than a clean run.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.utils.trigger_rule import TriggerRule

sys.path.insert(0, "/opt/airflow")

from src import pipeline, db  # noqa: E402

DATA_DIR = os.getenv("PIPELINE_DATA_DIR", "/opt/airflow/data")

default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}


def _paths(context) -> tuple[str, str, int | None]:
    """Read the run configuration passed when the DAG is triggered."""
    conf = context["dag_run"].conf or {}
    input_path = conf.get("input_path") or os.path.join(DATA_DIR, "samples", "sales_messy.csv")
    dataset_id = conf.get("dataset_id")
    name = os.path.basename(input_path).replace(".csv", "_cleaned.csv")
    output_path = conf.get("output_path") or os.path.join(DATA_DIR, "output", name)
    return input_path, output_path, dataset_id


def profile_data(**context):
    input_path, _, dataset_id = _paths(context)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input CSV not found: {input_path}")
    profile = pipeline.step_profile(input_path, dataset_id)
    context["ti"].xcom_push(key="profile", value=profile)
    return profile["needs_cleaning"]


def branch_on_quality(**context):
    profile = context["ti"].xcom_pull(key="profile", task_ids="profile_data")
    return "generate_ai_plan" if profile["needs_cleaning"] else "skip_ai_planning"


def generate_ai_plan(**context):
    profile = context["ti"].xcom_pull(key="profile", task_ids="profile_data")
    plan = pipeline.step_plan(profile)
    context["ti"].xcom_push(key="plan", value=plan)
    return plan


def skip_ai_planning(**context):
    empty = {"steps": [], "source": "skipped_clean"}
    context["ti"].xcom_push(key="plan", value=empty)
    return empty


def validate_plan(**context):
    ti = context["ti"]
    profile = ti.xcom_pull(key="profile", task_ids="profile_data")
    plan = ti.xcom_pull(key="plan", task_ids="generate_ai_plan")
    if plan is None:
        plan = ti.xcom_pull(key="plan", task_ids="skip_ai_planning")
    validated = pipeline.step_validate(plan, profile)
    validated["source"] = plan.get("source", "unknown")
    ti.xcom_push(key="validated", value=validated)
    return validated


def clean_data(**context):
    input_path, output_path, dataset_id = _paths(context)
    validated = context["ti"].xcom_pull(key="validated", task_ids="validate_plan")
    cleaned, log = pipeline.step_clean(input_path, validated, output_path, dataset_id)
    context["ti"].xcom_push(
        key="shape", value={"rows": int(cleaned.shape[0]), "cols": int(cleaned.shape[1])}
    )
    return len(log)


def analyze_data(**context):
    _, output_path, dataset_id = _paths(context)
    results = pipeline.step_analyze(output_path, dataset_id)
    return results["row_count"]


def finalize(**context):
    _, output_path, dataset_id = _paths(context)
    shape = context["ti"].xcom_pull(key="shape", task_ids="clean_data")
    if dataset_id:
        db.finalize_dataset(dataset_id, shape["rows"], shape["cols"], output_path)
    print(f"[finalize] Dataset {dataset_id} complete: {shape}")


with DAG(
    dag_id="csv_cleaning_pipeline",
    description="Profile, AI-plan, validate, clean and analyze an uploaded CSV",
    default_args=default_args,
    start_date=datetime(2026, 9, 1),
    schedule=None,  # triggered per upload by the API, not on a timer
    catchup=False,
    max_active_runs=4,
    tags=["data-engineering", "ai", "etl"],
) as dag:

    t_profile = PythonOperator(task_id="profile_data", python_callable=profile_data)

    t_branch = BranchPythonOperator(task_id="branch_on_quality", python_callable=branch_on_quality)

    t_ai = PythonOperator(task_id="generate_ai_plan", python_callable=generate_ai_plan)

    t_skip = PythonOperator(task_id="skip_ai_planning", python_callable=skip_ai_planning)

    # NONE_FAILED_MIN_ONE_SUCCESS lets this run after whichever branch executed.
    t_validate = PythonOperator(
        task_id="validate_plan",
        python_callable=validate_plan,
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    t_clean = PythonOperator(task_id="clean_data", python_callable=clean_data)
    t_analyze = PythonOperator(task_id="analyze_data", python_callable=analyze_data)
    t_finalize = PythonOperator(task_id="finalize", python_callable=finalize)

    t_profile >> t_branch >> [t_ai, t_skip] >> t_validate >> t_clean >> t_analyze >> t_finalize
