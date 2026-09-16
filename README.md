# AI Data Cleaning & Analytics Platform

Upload a CSV — clean or messy. The platform profiles it, an AI proposes a cleaning
plan, every proposed step is **verified against the measured data before anything is
applied**, and you get back cleaned data plus an interactive dashboard with exports.

---

## The Problem

Most people working with data spend the majority of their time cleaning it, and most
automated cleaning tools are black boxes: data goes in, different data comes out, and
you have no record of what changed or why. When an AI is doing the cleaning, that
opacity becomes a real risk — a model that confidently invents a column name or
misstates a null count will silently corrupt a dataset.

This platform separates the two concerns:

- **The AI reasons.** It receives a statistical profile and proposes a cleaning plan.
- **The pipeline verifies and executes.** Every proposed step is checked against the
  measured profile. Steps that reference non-existent columns, invented counts, or
  inapplicable operations are **rejected and logged**, not applied.

The result is a cleaning process that is both intelligent and auditable.

---

## Architecture

```
  Browser
     |  upload CSV
     v
  Next.js (Vercel) ----------> Supabase Storage (raw file)
     |                                |
     |  trigger DAG                   |
     v                                v
  Airflow (Docker) -------------------+
     |
     |  profile_data          deterministic measurement (no AI)
     |       |
     |  branch_on_quality     clean file? -> skip the AI entirely
     |       |
     |  generate_ai_plan      AI sees column STATISTICS, never raw data
     |       |
     |  validate_plan         rejects hallucinated steps  <-- the key gate
     |       |
     |  clean_data            executes only validated steps, logs real numbers
     |       |
     |  analyze_data          same analysis for both paths
     |       |
     +--> Supabase (Postgres): datasets, cleaning_logs, analysis_results
                |
                v
     Next.js dashboard: filterable charts, cleaning log, exports
                |
                +--> cleaned CSV | Parquet | Power BI package | PDF

  Spark (Docker, optional profile): engages above SPARK_ROW_THRESHOLD rows
```

---

## Quick Start

```bash
# 1. Generate sample data (one clean file, one deliberately messy)
python scripts/make_samples.py

# 2. Run the pipeline with no Docker, no Airflow, no database
python scripts/run_local.py data/samples/sales_messy.csv

# 3. Start the full stack
cp .env.example .env          # add your GEMINI_API_KEY
docker compose up

#    Airflow UI:  http://localhost:8080   (admin / admin)
#    Postgres:    localhost:5433

# 4. Start the frontend
cd frontend
cp .env.local.example .env.local   # add your Supabase keys
npm install
npm run dev                        # http://localhost:3000
```

**Start with step 2.** It runs the entire pipeline in about two seconds with no
infrastructure. That is your fastest feedback loop while building — use it constantly
and only bring Docker up when you are actually testing orchestration.

---

## File Placement

| File | Path | Purpose |
| --- | --- | --- |
| `profiler.py` | `src/profiler.py` | Deterministic measurement — the ground truth |
| `ai_planner.py` | `src/ai_planner.py` | The only AI call; returns a structured plan |
| `validator.py` | `src/validator.py` | Rejects hallucinated steps before execution |
| `cleaner.py` | `src/cleaner.py` | Executes validated steps, logs real before/after |
| `analyzer.py` | `src/analyzer.py` | Summary stats, correlations, charts, time series |
| `exporters.py` | `src/exporters.py` | CSV, Parquet, Power BI package |
| `spark_job.py` | `src/spark_job.py` | Distributed path for large files |
| `pipeline.py` | `src/pipeline.py` | Step functions, callable from CLI or Airflow |
| `db.py` | `src/db.py` | Postgres/Supabase access |
| `csv_cleaning_dag.py` | `dags/csv_cleaning_dag.py` | Airflow orchestration |
| `schema.sql` | `sql/schema.sql` | Database schema |
| `Dockerfile` | `Dockerfile` | Airflow image with pipeline dependencies |
| `docker-compose.yml` | `docker-compose.yml` | Postgres + Airflow + Spark stack |
| `make_samples.py` | `scripts/make_samples.py` | Generates clean and messy test CSVs |
| `run_local.py` | `scripts/run_local.py` | CLI runner, no infrastructure needed |
| `supabase.ts` | `frontend/lib/supabase.ts` | Supabase clients and types |
| `page.tsx` | `frontend/app/page.tsx` | Upload page with status polling |
| `page.tsx` | `frontend/app/dashboard/page.tsx` | Dashboard with filters and exports |
| `route.ts` | `frontend/app/api/upload/route.ts` | Upload + DAG trigger |
| `route.ts` | `frontend/app/api/datasets/route.ts` | Dataset, logs, analysis |
| `route.ts` | `frontend/app/api/export/route.ts` | CSV / Parquet / Power BI download |
| `layout.tsx` | `frontend/app/layout.tsx` | Root layout |
| `globals.css` | `frontend/app/globals.css` | Tailwind + print styles for PDF export |

---

## How Each Tool You've Studied Is Actually Used

This section exists so you can answer "where did you use X?" without hesitating.

### Docker
- `Dockerfile` builds a custom Airflow image with the pipeline's dependencies layered on
- `docker-compose.yml` runs Postgres, Airflow webserver, and Airflow scheduler together
- Spark sits behind a **profile** (`docker compose --profile spark up`) so it doesn't
  slow your normal dev loop
- **Practical thing to do:** intentionally break the Dockerfile (remove `libpq-dev`),
  watch the build fail, fix it. Understanding *why* it failed is the learning.

### Airflow
- `dags/csv_cleaning_dag.py` orchestrates the pipeline with retries, logging, and a
  `BranchPythonOperator` that routes clean files around the AI
- Data moves between tasks via **XCom** (small JSON only — profiles, plans, logs).
  Files move via the shared volume. Sending a dataframe through XCom is a classic
  mistake; this project deliberately doesn't.
- `TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS` on `validate_plan` lets it run after
  whichever branch executed
- **Practical thing to do:** upload a deliberately malformed CSV, watch `profile_data`
  fail, confirm nothing corrupt reached the database, screenshot the red task.
  **That screenshot is worth more in a demo than a clean green run.**

### SQL / PostgreSQL
- `sql/schema.sql` defines three tables with foreign keys, `ON DELETE CASCADE`, JSONB
  columns for flexible profile/detail storage, and indexes on the columns you actually
  query by
- **Practical thing to do:** after a run, connect and query the log yourself:
  ```sql
  SELECT status, action, reason FROM cleaning_logs WHERE dataset_id = 1;
  SELECT count(*) FROM cleaning_logs WHERE status = 'rejected';
  ```

### Python / pandas
- The entire profiling, cleaning, and analysis layer
- Note `cleaner.py` uses an `_is_text()` helper rather than `dtype == object` —
  that check breaks on newer pandas where string columns get a dedicated dtype.
  Small detail, real bug, worth knowing.

### Spark
- `src/spark_job.py` handles the distributed path above `SPARK_ROW_THRESHOLD` rows
- Uses `approxQuantile` rather than an exact median, because an exact median forces a
  full sort across the cluster
- **Be honest in your demo:** for a 3,000-row CSV, Spark is *slower* than pandas
  because of JVM startup. Spark earns its place when data no longer fits in memory.
  Showing you know *when* to reach for Spark is worth more than forcing it everywhere.

### Supabase
- Storage for raw and cleaned files, Postgres for structured data
- Note the two clients in `frontend/lib/supabase.ts`: the anon key is safe in the
  browser, the service role key **bypasses RLS** and must never leave the server

### Next.js / Vercel
- Upload page with drag-drop and polling; dashboard with filterable charts
- The upload route returns as soon as the DAG is triggered rather than waiting for the
  pipeline — a route that blocks for 90 seconds will hit serverless timeouts

---

## On the Power BI Export — Read This Before You Present

A `.pbix` file is a proprietary, undocumented container. There is no supported library
that generates one from scratch. **Claiming your app "exports a real Power BI file" is
the kind of claim that falls apart in live Q&A.**

What this project does instead is what real data teams do: export the cleaned data as
CSV and Parquet (both native Power BI import formats) plus a generated model guide with
the table schema and suggested DAX measures. Power BI connects in two clicks.

Describe it as **"Power BI ready export with a documented model."** That's accurate,
sounds professional, and you can defend every word.

---

## Demo Script (5 minutes)

1. **Upload the clean file.** Point out the Airflow DAG branching *around* the AI —
   "a clean file shouldn't cost an API call." Cost-awareness reads as maturity.
2. **Upload the messy file.** Walk through the cleaning log: 120 duplicates removed,
   251 nulls filled with the column mean, 27 outliers clipped, dates parsed.
3. **Show a rejected step.** This is your strongest moment. Explain that the AI
   proposed a step referencing a column that didn't exist, and the validator caught it
   against the measured profile. *The AI advises, the pipeline verifies.*
4. **Show the dashboard filters** — switch chart type, change the measure, change top-N.
5. **Show the exports** — cleaned CSV, Power BI package, PDF.
6. **Show the failed DAG run** from the malformed CSV. "Corrupt data never reached the
   database."

---

## What I'd Improve Next

- The validator's rules are hand-written; a larger rule set would benefit from being
  config-driven rather than code-driven
- Outlier clipping uses IQR uniformly — some distributions would be better served by
  a z-score or domain-specific bounds, and the AI could reasonably choose between them
- No user accounts yet; datasets are currently global rather than per-user, which
  would need RLS policies before any real deployment
- The Spark threshold is a single row count; file size and column count would make a
  better heuristic
