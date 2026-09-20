"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import type { Dataset } from "@/lib/supabase";

type Status = "idle" | "uploading" | "processing" | "complete" | "failed";

// Order matters - this drives the progress bar's percentage.
const STAGE_ORDER = [
  "queued",
  "profiling",
  "planning",
  "validating",
  "cleaning",
  "analyzing",
  "exporting",
  "complete",
];

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  profiling: "Profiling data",
  planning: "Planning cleaning steps",
  validating: "Validating plan",
  cleaning: "Cleaning data",
  analyzing: "Analyzing",
  exporting: "Preparing downloads",
  complete: "Complete",
  failed: "Failed",
};

// If a stage hasn't advanced in this many seconds, tell the user something
// looks stuck instead of leaving them staring at a frozen list.
const STUCK_THRESHOLD_SECONDS = 40;
const POLL_INTERVAL_MS = 2000;

function stagePercent(stage: string): number {
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx === -1) return 0;
  return Math.round((idx / (STAGE_ORDER.length - 1)) * 100);
}

export default function UploadPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("idle");
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const [elapsed, setElapsed] = useState(0); // seconds since upload started
  const [stageElapsed, setStageElapsed] = useState(0); // seconds since current stage began
  const startedAtRef = useRef<number>(0);

  const upload = useCallback(async (file: File) => {
    setError(null);
    setStatus("uploading");

    const body = new FormData();
    body.append("file", file);

    try {
      const res = await fetch("/api/upload", { method: "POST", body });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error ?? "Upload failed.");
        setStatus("failed");
        return;
      }

      startedAtRef.current = Date.now();
      setElapsed(0);
      setStageElapsed(0);
      setDatasetId(data.dataset_id);
      setStatus("processing");
    } catch {
      setError("Could not reach the server. Check your connection and try again.");
      setStatus("failed");
    }
  }, []);

  // Poll the REAL pipeline stage from the database - not a fake counter.
  useEffect(() => {
    if (status !== "processing" || !datasetId) return;

    const poll = async () => {
      try {
        const res = await fetch(`/api/datasets?id=${datasetId}`);
        const data = await res.json();
        const ds: Dataset | undefined = data.dataset;
        if (!ds) return;

        setDataset(ds);

        if (ds.status === "complete") {
          setStatus("complete");
          router.push(`/dashboard?id=${datasetId}`);
        } else if (ds.status === "failed") {
          setError(ds.error ?? "The pipeline failed.");
          setStatus("failed");
        }
      } catch {
        // Transient network errors during polling are not fatal - keep polling.
      }
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [status, datasetId, router]);

  // Elapsed-time and stage-elapsed ticking, independent of the poll interval
  // so the timer feels live even between polls.
  useEffect(() => {
    if (status !== "processing") return;

    const tick = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      if (dataset?.stage_updated_at) {
        const since = Date.now() - new Date(dataset.stage_updated_at).getTime();
        setStageElapsed(Math.floor(since / 1000));
      }
    }, 1000);

    return () => clearInterval(tick);
  }, [status, dataset]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  };

  const stage = dataset?.current_stage ?? "queued";
  const percent = stagePercent(stage);
  const isStuck = status === "processing" && stageElapsed >= STUCK_THRESHOLD_SECONDS;

  return (
    <main className="min-h-screen bg-neutral-50 px-6 py-16">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-semibold text-neutral-900">
          Upload a CSV
        </h1>
        <p className="mt-2 text-neutral-600">
          Clean or messy. Messy files are profiled, an AI proposes a cleaning
          plan, and every proposed step is verified against the real data before
          anything is applied.
        </p>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`mt-8 rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
            dragging
              ? "border-neutral-900 bg-neutral-100"
              : "border-neutral-300 bg-white"
          }`}
        >
          <p className="text-neutral-700">Drag a .csv file here</p>
          <p className="my-3 text-sm text-neutral-400">or</p>
          <label className="inline-block cursor-pointer rounded bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700">
            Choose file
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload(file);
              }}
            />
          </label>
          <p className="mt-4 text-xs text-neutral-400">Maximum 50 MB</p>
        </div>

        {status === "uploading" && (
          <p className="mt-6 text-sm text-neutral-600">Uploading file...</p>
        )}

        {status === "processing" && (
          <div className="mt-6 rounded border border-neutral-200 bg-white p-5">
            <div className="mb-3 flex items-baseline justify-between">
              <p className="text-sm font-medium text-neutral-900">
                {STAGE_LABELS[stage] ?? stage}
              </p>
              <p className="text-xs text-neutral-400">
                {elapsed}s elapsed
              </p>
            </div>

            {/* Real progress bar, driven by the actual stage from the database */}
            <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100">
              <div
                className="h-full rounded-full bg-neutral-900 transition-all duration-700 ease-out"
                style={{ width: `${Math.max(percent, 5)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-neutral-400">{percent}%</p>

            <ul className="mt-4 space-y-1.5">
              {STAGE_ORDER.slice(1, -1).map((s) => {
                const idx = STAGE_ORDER.indexOf(s);
                const currentIdx = STAGE_ORDER.indexOf(stage);
                const done = idx < currentIdx;
                const active = s === stage;
                return (
                  <li
                    key={s}
                    className={`text-sm ${
                      done || active ? "text-neutral-900" : "text-neutral-400"
                    }`}
                  >
                    {done ? "[done] " : active ? "[running] " : "[    ] "}
                    {STAGE_LABELS[s]}
                    {active && isStuck && (
                      <span className="ml-2 text-amber-600">
                        - still working, {stageElapsed}s on this step
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>

            {isStuck && (
              <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm text-amber-900">
                  This step is taking longer than usual ({stageElapsed}s). The
                  pipeline may still be working on a large file, or it may be
                  stuck. If this continues past a minute or two, check the
                  Airflow logs for this run, or try again.
                </p>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-6 rounded border border-red-200 bg-red-50 p-4">
            <p className="text-sm font-medium text-red-900">Something failed</p>
            <p className="mt-1 text-sm text-red-700">{error}</p>
            <button
              onClick={() => {
                setStatus("idle");
                setError(null);
                setDataset(null);
                setElapsed(0);
                setStageElapsed(0);
              }}
              className="mt-3 rounded border border-red-300 px-3 py-1.5 text-sm text-red-900 hover:bg-red-100"
            >
              Try again
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
