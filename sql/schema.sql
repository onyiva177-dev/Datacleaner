-- Schema for the AI Data Cleaning and Analytics platform.
-- Works unchanged on local Postgres (docker compose) and on Supabase.

CREATE TABLE IF NOT EXISTS datasets (
    id                BIGSERIAL PRIMARY KEY,
    filename          TEXT        NOT NULL,
    original_rows     INTEGER,
    original_columns  INTEGER,
    cleaned_rows      INTEGER,
    cleaned_columns   INTEGER,
    cleaned_path      TEXT,
    profile           JSONB,
    status            TEXT        NOT NULL DEFAULT 'pending',
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

-- The audit trail. One row per cleaning step, including rejected ones.
-- This table is the feature that makes the project defensible: it proves
-- the AI advised and the pipeline verified.
CREATE TABLE IF NOT EXISTS cleaning_logs (
    id            BIGSERIAL PRIMARY KEY,
    dataset_id    BIGINT      NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    column_name   TEXT,
    action        TEXT        NOT NULL,
    reason        TEXT,
    status        TEXT        NOT NULL,   -- applied | rejected | failed
    error         TEXT,
    rows_before   INTEGER,
    rows_after    INTEGER,
    detail        JSONB       NOT NULL DEFAULT '{}'::JSONB,
    plan_source   TEXT,                   -- ai | fallback | skipped_clean
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id          BIGSERIAL PRIMARY KEY,
    dataset_id  BIGINT      NOT NULL UNIQUE REFERENCES datasets(id) ON DELETE CASCADE,
    results     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cleaning_logs_dataset ON cleaning_logs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_datasets_status      ON datasets(status);
CREATE INDEX IF NOT EXISTS idx_datasets_created     ON datasets(created_at DESC);
