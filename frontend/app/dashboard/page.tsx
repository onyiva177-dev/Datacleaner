"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { Analysis, CleaningLogEntry, Dataset } from "@/lib/supabase";

const PALETTE = ["#1f2937", "#4b5563", "#6b7280", "#9ca3af", "#d1d5db", "#374151"];

type ChartKind = "bar" | "line" | "pie";

export default function DashboardPage() {
  const params = useSearchParams();
  const id = params.get("id");

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [logs, setLogs] = useState<CleaningLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedCategorical, setSelectedCategorical] = useState<string>("");
  const [selectedDistribution, setSelectedDistribution] = useState<string>("");
  const [selectedSeries, setSelectedSeries] = useState<string>("");
  const [chartKind, setChartKind] = useState<ChartKind>("bar");
  const [topN, setTopN] = useState(10);
  const [logFilter, setLogFilter] = useState<"all" | "applied" | "rejected">("all");

  useEffect(() => {
    if (!id) {
      setError("No dataset selected.");
      setLoading(false);
      return;
    }
    fetch(`/api/datasets?id=${id}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setError(data.error);
        } else {
          setDataset(data.dataset);
          setAnalysis(data.analysis);
          setLogs(data.logs ?? []);
          setSelectedCategorical(data.analysis?.categorical?.[0]?.column ?? "");
          setSelectedDistribution(data.analysis?.distributions?.[0]?.column ?? "");
          setSelectedSeries(data.analysis?.time_series?.[0]?.value_column ?? "");
        }
      })
      .catch(() => setError("Could not load the dataset."))
      .finally(() => setLoading(false));
  }, [id]);

  const categoricalData = useMemo(() => {
    const found = analysis?.categorical.find((c) => c.column === selectedCategorical);
    return (found?.data ?? []).slice(0, topN);
  }, [analysis, selectedCategorical, topN]);

  const distributionData = useMemo(
    () => analysis?.distributions.find((d) => d.column === selectedDistribution)?.data ?? [],
    [analysis, selectedDistribution]
  );

  const seriesData = useMemo(
    () => analysis?.time_series.find((s) => s.value_column === selectedSeries)?.data ?? [],
    [analysis, selectedSeries]
  );

  const visibleLogs = useMemo(
    () => (logFilter === "all" ? logs : logs.filter((l) => l.status === logFilter)),
    [logs, logFilter]
  );

  const appliedCount = logs.filter((l) => l.status === "applied").length;
  const rejectedCount = logs.filter((l) => l.status === "rejected").length;

  if (loading) return <Shell><p className="text-neutral-500">Loading dashboard...</p></Shell>;
  if (error) return <Shell><p className="text-red-700">{error}</p></Shell>;
  if (!analysis) return <Shell><p className="text-neutral-500">No analysis available yet.</p></Shell>;

  return (
    <Shell>
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900">
            {dataset?.filename}
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            {dataset?.original_rows?.toLocaleString()} rows in,{" "}
            {analysis.row_count.toLocaleString()} rows out, {analysis.column_count} columns
          </p>
        </div>
        <div className="flex gap-2 print:hidden">
          <a
            href={`/api/export?id=${id}&format=csv`}
            className="rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100"
          >
            Cleaned CSV
          </a>
          <a
            href={`/api/export?id=${id}&format=powerbi`}
            className="rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100"
          >
            Power BI package
          </a>
          <button
            onClick={() => window.print()}
            className="rounded bg-neutral-900 px-3 py-2 text-sm text-white hover:bg-neutral-700"
          >
            Export PDF
          </button>
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Rows" value={analysis.row_count.toLocaleString()} />
        <Stat label="Columns" value={String(analysis.column_count)} />
        <Stat label="Steps applied" value={String(appliedCount)} />
        <Stat label="Steps rejected" value={String(rejectedCount)} />
      </div>

      {/* Categorical breakdown with chart-type and top-N filters */}
      {analysis.categorical.length > 0 && (
        <Panel title="Breakdown by category">
          <div className="mb-4 flex flex-wrap gap-3 print:hidden">
            <Select
              label="Column"
              value={selectedCategorical}
              onChange={setSelectedCategorical}
              options={analysis.categorical.map((c) => c.column)}
            />
            <Select
              label="Chart"
              value={chartKind}
              onChange={(v) => setChartKind(v as ChartKind)}
              options={["bar", "line", "pie"]}
            />
            <Select
              label="Show top"
              value={String(topN)}
              onChange={(v) => setTopN(Number(v))}
              options={["5", "10", "12"]}
            />
          </div>
          <ResponsiveContainer width="100%" height={320}>
            {chartKind === "bar" ? (
              <BarChart data={categoricalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#1f2937" />
              </BarChart>
            ) : chartKind === "line" ? (
              <LineChart data={categoricalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#1f2937" strokeWidth={2} />
              </LineChart>
            ) : (
              <PieChart>
                <Pie data={categoricalData} dataKey="value" nameKey="label" outerRadius={110} label>
                  {categoricalData.map((_, i) => (
                    <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            )}
          </ResponsiveContainer>
        </Panel>
      )}

      {/* Time series */}
      {analysis.time_series.length > 0 && (
        <Panel title="Trend over time">
          <div className="mb-4 print:hidden">
            <Select
              label="Measure"
              value={selectedSeries}
              onChange={setSelectedSeries}
              options={analysis.time_series.map((s) => s.value_column)}
            />
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={seriesData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={40} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#1f2937" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {/* Distributions */}
      {analysis.distributions.length > 0 && (
        <Panel title="Distribution">
          <div className="mb-4 print:hidden">
            <Select
              label="Column"
              value={selectedDistribution}
              onChange={setSelectedDistribution}
              options={analysis.distributions.map((d) => d.column)}
            />
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={distributionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#4b5563" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      {/* The cleaning log - the differentiating feature */}
      <Panel title="Cleaning log">
        <p className="mb-3 text-sm text-neutral-600">
          Every step the planner proposed, and whether the validator allowed it.
          Rejected steps were caught because they did not match the measured data.
        </p>
        <div className="mb-4 flex gap-2 print:hidden">
          {(["all", "applied", "rejected"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setLogFilter(f)}
              className={`rounded border px-3 py-1.5 text-sm ${
                logFilter === f
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-300 hover:bg-neutral-100"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-neutral-200 text-neutral-500">
              <tr>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium">Column</th>
                <th className="py-2 pr-4 font-medium">Action</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {visibleLogs.map((log) => (
                <tr key={log.id} className="border-b border-neutral-100">
                  <td className="py-2 pr-4">
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        log.status === "applied"
                          ? "bg-neutral-900 text-white"
                          : log.status === "rejected"
                          ? "bg-amber-100 text-amber-900"
                          : "bg-red-100 text-red-900"
                      }`}
                    >
                      {log.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-neutral-700">{log.column_name ?? "(table)"}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-neutral-700">{log.action}</td>
                  <td className="py-2 text-neutral-600">{log.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Summary statistics */}
      <Panel title="Summary statistics">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-neutral-200 text-neutral-500">
              <tr>
                <th className="py-2 pr-4 font-medium">Column</th>
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 pr-4 font-medium">Non-null</th>
                <th className="py-2 pr-4 font-medium">Unique</th>
                <th className="py-2 pr-4 font-medium">Mean</th>
                <th className="py-2 font-medium">Median</th>
              </tr>
            </thead>
            <tbody>
              {analysis.summary_stats.map((s) => (
                <tr key={s.column} className="border-b border-neutral-100">
                  <td className="py-2 pr-4 text-neutral-900">{s.column}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-neutral-500">{s.dtype}</td>
                  <td className="py-2 pr-4 text-neutral-700">{s.non_null.toLocaleString()}</td>
                  <td className="py-2 pr-4 text-neutral-700">{s.unique.toLocaleString()}</td>
                  <td className="py-2 pr-4 text-neutral-700">{s.mean ?? "-"}</td>
                  <td className="py-2 text-neutral-700">{s.median ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-neutral-50 px-6 py-12">
      <div className="mx-auto max-w-5xl">{children}</div>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6 rounded-lg border border-neutral-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium text-neutral-900">{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-neutral-900">{value}</p>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-neutral-600">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm text-neutral-900"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
