"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

type Status = "idle" | "uploading" | "processing" | "complete" | "failed";

const STAGES = [
  "Profiling data",
  "Planning cleaning steps",
  "Validating plan",
  "Cleaning data",
  "Analyzing",
];

export default function UploadPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("idle");
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState(0);

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

      setDatasetId(data.dataset_id);
      setStatus("processing");
    } catch {
      setError("Could not reach the server. Check your connection and try again.");
      setStatus("failed");
    }
  }, []);

  // Poll for completion. Stops as soon as the pipeline reaches a terminal state.
  useEffect(() => {
    if (status !== "processing" || !datasetId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/datasets?id=${datasetId}`);
        const data = await res.json();

        if (data.dataset?.status === "complete") {
          clearInterval(interval);
          setStatus("complete");
          router.push(`/dashboard?id=${datasetId}`);
        } else if (data.dataset?.status === "failed") {
          clearInterval(interval);
          setError(data.dataset.error ?? "The pipeline failed.");
          setStatus("failed");
        } else {
          setStage((s) => Math.min(s + 1, STAGES.length - 1));
        }
      } catch {
        // Transient network errors during polling are not fatal - keep polling.
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [status, datasetId, router]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  };

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
            <p className="text-sm font-medium text-neutral-900">
              Pipeline running
            </p>
            <ul className="mt-3 space-y-1.5">
              {STAGES.map((label, i) => (
                <li
                  key={label}
                  className={`text-sm ${
                    i <= stage ? "text-neutral-900" : "text-neutral-400"
                  }`}
                >
                  {i < stage ? "[done] " : i === stage ? "[running] " : "[    ] "}
                  {label}
                </li>
              ))}
            </ul>
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
                setStage(0);
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
