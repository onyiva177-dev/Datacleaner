import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase";

export const runtime = "nodejs";

/**
 * GET /api/export?id=12&format=csv      -> cleaned CSV download
 * GET /api/export?id=12&format=parquet  -> Parquet download
 * GET /api/export?id=12&format=powerbi  -> Power BI model guide (markdown)
 *
 * The pipeline writes these artifacts to Supabase Storage under
 * cleaned/<dataset_id>/. This route creates a short-lived signed URL and
 * redirects - streaming large files through a serverless function would be
 * slower and can hit response size limits.
 */
export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get("id");
  const format = (req.nextUrl.searchParams.get("format") ?? "csv").toLowerCase();

  if (!id || !Number.isInteger(Number(id))) {
    return NextResponse.json({ error: "Invalid dataset id." }, { status: 400 });
  }

  const fileMap: Record<string, string> = {
    csv: "cleaned.csv",
    parquet: "cleaned.parquet",
    powerbi: "powerbi_model.md",
    analysis: "analysis.json",
  };

  const filename = fileMap[format];
  if (!filename) {
    return NextResponse.json(
      { error: `Unsupported format '${format}'. Use csv, parquet, powerbi or analysis.` },
      { status: 400 }
    );
  }

  try {
    const db = supabaseAdmin();
    const path = `cleaned/${id}/${filename}`;

    const { data, error } = await db.storage
      .from("datasets")
      .createSignedUrl(path, 60, { download: true });

    if (error || !data) {
      return NextResponse.json(
        { error: `Export not available yet: ${error?.message ?? "file not found"}` },
        { status: 404 }
      );
    }

    return NextResponse.redirect(data.signedUrl);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
