"""
Database access. Works against local Postgres (docker compose) or Supabase -
both are Postgres, so the same psycopg2 connection code serves both. You only
change the connection env vars.
"""
from __future__ import annotations

import json
import os

import psycopg2
from psycopg2.extras import Json, RealDictCursor


def get_connection():
    """
    Local docker compose uses POSTGRES_* vars.
    Supabase uses a full connection string - set DATABASE_URL and it wins.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "datacleaner"),
        user=os.getenv("POSTGRES_USER", "datacleaner"),
        password=os.getenv("POSTGRES_PASSWORD", "datacleaner"),
    )


def create_dataset(filename: str, original_rows: int, original_cols: int) -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO datasets (filename, original_rows, original_columns, status)
            VALUES (%s, %s, %s, 'processing')
            RETURNING id
            """,
            (filename, original_rows, original_cols),
        )
        return cur.fetchone()[0]


def save_profile(dataset_id: int, profile: dict) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE datasets SET profile = %s WHERE id = %s",
            (Json(profile), dataset_id),
        )


def save_cleaning_log(dataset_id: int, log: list, plan_source: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        for entry in log:
            cur.execute(
                """
                INSERT INTO cleaning_logs
                    (dataset_id, column_name, action, reason, status, error,
                     rows_before, rows_after, detail, plan_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    dataset_id,
                    entry.get("column"),
                    entry.get("action"),
                    entry.get("reason"),
                    entry.get("status"),
                    entry.get("error"),
                    entry.get("rows_before"),
                    entry.get("rows_after"),
                    Json(entry.get("detail") or {}),
                    plan_source,
                ),
            )


def save_analysis(dataset_id: int, analysis: dict) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO analysis_results (dataset_id, results)
            VALUES (%s, %s)
            ON CONFLICT (dataset_id) DO UPDATE SET results = EXCLUDED.results
            """,
            (dataset_id, Json(analysis)),
        )


def finalize_dataset(dataset_id: int, cleaned_rows: int, cleaned_cols: int,
                     cleaned_path: str, status: str = "complete") -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE datasets
               SET cleaned_rows = %s,
                   cleaned_columns = %s,
                   cleaned_path = %s,
                   status = %s,
                   completed_at = NOW()
             WHERE id = %s
            """,
            (cleaned_rows, cleaned_cols, cleaned_path, status, dataset_id),
        )


def mark_failed(dataset_id: int, error: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE datasets SET status = 'failed', error = %s WHERE id = %s",
            (error[:2000], dataset_id),
        )


def get_dataset(dataset_id: int) -> dict | None:
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM datasets WHERE id = %s", (dataset_id,))
        return cur.fetchone()
