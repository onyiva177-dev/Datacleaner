import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";

export const runtime = "nodejs";

/**
 * GET /api/datasets            -> list of datasets (newest first)
 * GET /api/datasets?id=12      -> one dataset with its cleaning log and analysis
 *
 * The UI polls the single-dataset form while status is 'pending' or
 * 'processing', then stops once it reaches 'complete' or 'failed'.
 */
export async function GET(req: NextRequest) {
  const db = supabaseAdmin();
  const id = req.nextUrl.searchParams.get("id");

  try {
    if (!id) {
      const { data, error } = await db
        .from("datasets")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(50);

      if (error) throw new Error(error.message);
      return NextResponse.json({ datasets: data ?? [] });
    }

    const datasetId = Number(id);
    if (!Number.isInteger(datasetId)) {
      return NextResponse.json({ error: "Invalid dataset id." }, { status: 400 });
    }

    const [datasetRes, logsRes, analysisRes] = await Promise.all([
      db.from("datasets").select("*").eq("id", datasetId).single(),
      db
        .from("cleaning_logs")
        .select("*")
        .eq("dataset_id", datasetId)
        .order("id", { ascending: true }),
      db.from("analysis_results").select("results").eq("dataset_id", datasetId).maybeSingle(),
    ]);

    if (datasetRes.error) {
      return NextResponse.json({ error: "Dataset not found." }, { status: 404 });
    }

    return NextResponse.json({
      dataset: datasetRes.data,
      logs: logsRes.data ?? [],
      analysis: analysisRes.data?.results ?? null,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
