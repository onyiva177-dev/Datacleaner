import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";

export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_BYTES = 50 * 1024 * 1024; // 50 MB

/**
 * Upload flow:
 *   1. Validate the file (type, size) before anything else
 *   2. Store the raw file in Supabase Storage
 *   3. Create the dataset row so the UI has something to poll immediately
 *   4. Trigger the Airflow DAG, passing the dataset id and file path
 *
 * The route returns as soon as the DAG is triggered. It does NOT wait for the
 * pipeline to finish - a long upload that blocks for 90 seconds is a bad
 * experience and will hit serverless timeouts on Vercel. The UI polls instead.
 */
export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ error: "No file provided." }, { status: 400 });
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      return NextResponse.json(
        { error: "Only .csv files are supported." },
        { status: 400 }
      );
    }
    if (file.size > MAX_BYTES) {
      return NextResponse.json(
        { error: `File is too large. Limit is ${MAX_BYTES / 1024 / 1024} MB.` },
        { status: 400 }
      );
    }

    const db = supabaseAdmin();
    const storagePath = `raw/${Date.now()}_${file.name.replace(/[^\w.\-]/g, "_")}`;

    const { error: uploadError } = await db.storage
      .from("datasets")
      .upload(storagePath, file, { contentType: "text/csv", upsert: false });

    if (uploadError) {
      return NextResponse.json(
        { error: `Storage upload failed: ${uploadError.message}` },
        { status: 500 }
      );
    }

    const { data: dataset, error: insertError } = await db
      .from("datasets")
      .insert({ filename: file.name, status: "pending" })
      .select()
      .single();

    if (insertError) {
      return NextResponse.json(
        { error: `Could not create dataset record: ${insertError.message}` },
        { status: 500 }
      );
    }

    const triggered = await triggerAirflow(dataset.id, storagePath);

    return NextResponse.json({
      dataset_id: dataset.id,
      filename: file.name,
      storage_path: storagePath,
      pipeline_triggered: triggered.ok,
      pipeline_message: triggered.message,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

/**
 * Airflow's REST API uses basic auth. In production put Airflow behind a
 * private network or a tunnel - do not expose port 8080 to the internet.
 */
async function triggerAirflow(datasetId: number, storagePath: string) {
  const base = process.env.AIRFLOW_BASE_URL;
  const user = process.env.AIRFLOW_USERNAME;
  const pass = process.env.AIRFLOW_PASSWORD;

  if (!base || !user || !pass) {
    return { ok: false, message: "Airflow not configured; dataset queued only." };
  }

  try {
    const res = await fetch(`${base}/api/v1/dags/csv_cleaning_pipeline/dagRuns`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Basic " + Buffer.from(`${user}:${pass}`).toString("base64"),
      },
      body: JSON.stringify({
        dag_run_id: `upload_${datasetId}_${Date.now()}`,
        conf: {
          dataset_id: datasetId,
          storage_path: storagePath,
          input_path: `/opt/airflow/data/uploads/${storagePath.split("/").pop()}`,
        },
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      return { ok: false, message: `Airflow returned ${res.status}: ${body.slice(0, 200)}` };
    }
    return { ok: true, message: "Pipeline triggered." };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return { ok: false, message: `Could not reach Airflow: ${message}` };
  }
}
