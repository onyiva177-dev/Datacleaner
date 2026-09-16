import { createClient } from "@supabase/supabase-js";

// Browser client: anon key only. Never put the service role key here -
// anything in NEXT_PUBLIC_* ships to the browser.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

// Server client: used inside API routes only. The service role key bypasses
// RLS, which is why it must never leave the server.
export function supabaseAdmin() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
  );
}

export type ChartPoint = { label: string; value: number };

export type Analysis = {
  row_count: number;
  column_count: number;
  columns: string[];
  summary_stats: Array<{
    column: string;
    dtype: string;
    non_null: number;
    unique: number;
    min?: number;
    max?: number;
    mean?: number;
    median?: number;
    std?: number;
  }>;
  correlations: Array<{ x: string; y: string; correlation: number }>;
  categorical: Array<{ column: string; data: ChartPoint[] }>;
  distributions: Array<{ column: string; data: ChartPoint[] }>;
  time_series: Array<{
    date_column: string;
    value_column: string;
    data: ChartPoint[];
  }>;
};

export type CleaningLogEntry = {
  id: number;
  column_name: string | null;
  action: string;
  reason: string;
  status: "applied" | "rejected" | "failed";
  error: string | null;
  rows_before: number | null;
  rows_after: number | null;
  detail: Record<string, unknown>;
  plan_source: string;
};

export type Dataset = {
  id: number;
  filename: string;
  original_rows: number | null;
  original_columns: number | null;
  cleaned_rows: number | null;
  cleaned_columns: number | null;
  cleaned_path: string | null;
  status: "pending" | "processing" | "complete" | "failed";
  error: string | null;
  created_at: string;
};
