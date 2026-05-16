"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Gauge,
  MonitorSmartphone,
  RefreshCw,
  Smartphone,
  TrendingDown,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  cwvApi,
  type CWVStatus,
  type CWVProblemPage,
  type CWVMobileDesktopRow,
} from "@/lib/api-client";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function fmtScore(score: number | null): string {
  if (score == null) return "—";
  return `${Math.round(score * 100)}`;
}

const STATUS_CONFIG: Record<
  CWVStatus,
  { label: string; bg: string; text: string; ring: string; Icon: React.ElementType }
> = {
  good: {
    label: "Good",
    bg: "bg-emerald-500/15",
    text: "text-emerald-400",
    ring: "border-emerald-500/30",
    Icon: CheckCircle2,
  },
  needs_improvement: {
    label: "Needs work",
    bg: "bg-amber-500/15",
    text: "text-amber-400",
    ring: "border-amber-500/30",
    Icon: AlertTriangle,
  },
  poor: {
    label: "Poor",
    bg: "bg-red-500/15",
    text: "text-red-400",
    ring: "border-red-500/30",
    Icon: AlertCircle,
  },
  unknown: {
    label: "Unknown",
    bg: "bg-slate-700/40",
    text: "text-slate-400",
    ring: "border-slate-600/40",
    Icon: AlertCircle,
  },
};

function StatusBadge({ status }: { status: CWVStatus }) {
  const cfg = STATUS_CONFIG[status];
  const { Icon } = cfg;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        cfg.bg,
        cfg.text,
        cfg.ring,
      )}
    >
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

function scoreColor(score: number | null): string {
  if (score == null) return "text-slate-500";
  const pct = score * 100;
  if (pct >= 90) return "text-emerald-400";
  if (pct >= 50) return "text-amber-400";
  return "text-red-400";
}

// ── Origin summary card ───────────────────────────────────────────────────────

function OriginCard({
  propertyId,
}: {
  propertyId: number;
}) {
  const [strategy, setStrategy] = useState<"mobile" | "desktop">("mobile");

  const { data, isLoading, error } = useQuery({
    queryKey: ["cwv-origin", propertyId, strategy],
    queryFn: () => cwvApi.getOrigin(propertyId, strategy),
    staleTime: 5 * 60 * 1000,
  });

  const metrics = data
    ? [
        { label: "LCP", value: fmtMs(data.lcp_ms), threshold: data.lcp_ms != null && data.lcp_ms <= 2500 ? "good" : data.lcp_ms != null && data.lcp_ms <= 4000 ? "needs_improvement" : "poor" },
        { label: "INP", value: fmtMs(data.inp_ms), threshold: data.inp_ms != null && data.inp_ms <= 200 ? "good" : data.inp_ms != null && data.inp_ms <= 500 ? "needs_improvement" : "poor" },
        { label: "CLS", value: data.cls != null ? data.cls.toFixed(3) : "—", threshold: data.cls != null && data.cls <= 0.1 ? "good" : data.cls != null && data.cls <= 0.25 ? "needs_improvement" : "poor" },
      ]
    : [];

  const metricColor = (threshold: string) => {
    if (threshold === "good") return "text-emerald-400";
    if (threshold === "needs_improvement") return "text-amber-400";
    return "text-red-400";
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge size={16} className="text-brand-400" />
          <h2 className="text-sm font-semibold text-white">Site-wide CWV (CrUX)</h2>
        </div>
        <div className="flex gap-1 rounded-lg border border-slate-700 p-0.5">
          {(["mobile", "desktop"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStrategy(s)}
              className={clsx(
                "flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition",
                strategy === s
                  ? "bg-slate-700 text-white"
                  : "text-slate-400 hover:text-white",
              )}
            >
              {s === "mobile" ? <Smartphone size={12} /> : <MonitorSmartphone size={12} />}
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <RefreshCw size={14} className="animate-spin" />
          Loading CrUX data...
        </div>
      )}
      {error && (
        <p className="text-sm text-red-400">
          Could not load origin CWV data. CrUX may not have enough data for this site.
        </p>
      )}
      {data && (
        <div className="flex items-center gap-6">
          <StatusBadge status={data.cwv_status} />
          <div className="flex gap-8">
            {metrics.map((m) => (
              <div key={m.label} className="text-center">
                <p className="text-xs text-slate-500">{m.label}</p>
                <p className={clsx("text-xl font-bold tabular-nums", metricColor(m.threshold))}>
                  {m.value}
                </p>
              </div>
            ))}
          </div>
          {data.audited_at && (
            <p className="ml-auto text-xs text-slate-600">
              Updated {new Date(data.audited_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Problem pages table ───────────────────────────────────────────────────────

function ProblemPagesTable({
  propertyId,
}: {
  propertyId: number;
}) {
  const [strategy, setStrategy] = useState<"mobile" | "desktop">("mobile");

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["cwv-problems", propertyId, strategy],
    queryFn: () => cwvApi.scanProblems(propertyId, { strategy, limit: 50 }),
    staleTime: 5 * 60 * 1000,
  });

  const pages = data?.pages ?? [];

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div className="flex items-center gap-2">
          <TrendingDown size={16} className="text-red-400" />
          <h2 className="text-sm font-semibold text-white">Pages needing attention</h2>
          {data && (
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
              {data.total}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1 rounded-lg border border-slate-700 p-0.5">
            {(["mobile", "desktop"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStrategy(s)}
                className={clsx(
                  "flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition",
                  strategy === s
                    ? "bg-slate-700 text-white"
                    : "text-slate-400 hover:text-white",
                )}
              >
                {s === "mobile" ? <Smartphone size={12} /> : <MonitorSmartphone size={12} />}
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-white transition"
          >
            <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 px-5 py-8 text-sm text-slate-500">
          <RefreshCw size={14} className="animate-spin" />
          Scanning pages...
        </div>
      )}
      {error && (
        <p className="px-5 py-8 text-sm text-red-400">Failed to load page audits.</p>
      )}
      {!isLoading && pages.length === 0 && (
        <div className="px-5 py-8 text-center">
          <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-500" />
          <p className="text-sm font-medium text-white">All audited pages are passing</p>
          <p className="mt-1 text-xs text-slate-500">
            No pages with poor or needs-improvement CWV were found.
          </p>
        </div>
      )}
      {pages.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-xs text-slate-500">
                <th className="px-5 py-3 text-left font-medium">Page</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">LCP</th>
                <th className="px-4 py-3 text-right font-medium">INP</th>
                <th className="px-4 py-3 text-right font-medium">CLS</th>
                <th className="px-4 py-3 text-right font-medium">Score</th>
                <th className="px-4 py-3 text-right font-medium">Audited</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {pages.map((page: CWVProblemPage) => (
                <tr
                  key={`${page.url}-${page.strategy}`}
                  className="hover:bg-slate-800/30 transition-colors"
                >
                  <td className="max-w-xs px-5 py-3">
                    <span
                      className="block truncate font-mono text-xs text-slate-300"
                      title={page.url}
                    >
                      {page.url}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={page.cwv_status} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {fmtMs(page.lcp_ms)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {fmtMs(page.inp_ms)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {page.cls != null ? page.cls.toFixed(3) : "—"}
                  </td>
                  <td
                    className={clsx(
                      "px-4 py-3 text-right tabular-nums font-semibold",
                      scoreColor(page.lighthouse_performance_score),
                    )}
                  >
                    {fmtScore(page.lighthouse_performance_score)}
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-slate-500">
                    {page.audited_at
                      ? new Date(page.audited_at).toLocaleDateString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Mobile vs desktop divergence ─────────────────────────────────────────────

function MobileDesktopTable({ propertyId }: { propertyId: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["cwv-mobile-desktop", propertyId],
    queryFn: () => cwvApi.getMobileDesktop(propertyId),
    staleTime: 5 * 60 * 1000,
  });

  const rows = data?.rows ?? [];

  if (isLoading) return null;
  if (error || rows.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900">
      <div className="flex items-center gap-2 border-b border-slate-800 px-5 py-4">
        <MonitorSmartphone size={16} className="text-amber-400" />
        <h2 className="text-sm font-semibold text-white">Mobile vs desktop divergence</h2>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          {rows.length}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-xs text-slate-500">
              <th className="px-5 py-3 text-left font-medium">Page</th>
              <th className="px-4 py-3 text-left font-medium">Mobile</th>
              <th className="px-4 py-3 text-right font-medium">Mobile LCP</th>
              <th className="px-4 py-3 text-left font-medium">Desktop</th>
              <th className="px-4 py-3 text-right font-medium">Desktop LCP</th>
              <th className="px-4 py-3 text-right font-medium">Gap</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {rows.map((row: CWVMobileDesktopRow) => (
              <tr key={row.url} className="hover:bg-slate-800/30 transition-colors">
                <td className="max-w-xs px-5 py-3">
                  <span
                    className="block truncate font-mono text-xs text-slate-300"
                    title={row.url}
                  >
                    {row.url}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={row.mobile_status} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                  {fmtMs(row.mobile_lcp_ms)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={row.desktop_status} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                  {fmtMs(row.desktop_lcp_ms)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold text-amber-400">
                  +{fmtMs(row.lcp_gap_ms)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PerformancePage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);

  return (
    <div className="flex h-screen bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header propertyId={propertyId} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-5xl space-y-6">
            {/* Header */}
            <div>
              <h1 className="flex items-center gap-2 text-xl font-bold text-white">
                <Gauge size={20} className="text-brand-400" />
                Core Web Vitals
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                Page speed and user experience signals from PageSpeed Insights audits.
              </p>
            </div>

            {/* Threshold reference */}
            <div className="flex flex-wrap gap-3">
              {[
                { label: "LCP", good: "≤2.5s", poor: ">4s" },
                { label: "INP", good: "≤200ms", poor: ">500ms" },
                { label: "CLS", good: "≤0.1", poor: ">0.25" },
              ].map((m) => (
                <div
                  key={m.label}
                  className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-1.5 text-xs"
                >
                  <span className="font-mono font-bold text-slate-300">{m.label}</span>
                  <span className="text-emerald-400">Good {m.good}</span>
                  <span className="text-slate-600">·</span>
                  <span className="text-red-400">Poor {m.poor}</span>
                </div>
              ))}
            </div>

            {/* Site-wide CrUX origin */}
            <OriginCard propertyId={propertyId} />

            {/* Problem pages */}
            <ProblemPagesTable propertyId={propertyId} />

            {/* Mobile vs desktop */}
            <MobileDesktopTable propertyId={propertyId} />
          </div>
        </main>
      </div>
    </div>
  );
}
