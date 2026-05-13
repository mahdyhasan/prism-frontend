"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Lightbulb,
  RefreshCw,
  Sparkles,
  Split,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  insightsApi,
  type InsightKind,
  type InsightResponse,
  type InsightSeverity,
  type InsightStatus,
} from "@/lib/api-client";

type StatusFilter = "all" | InsightStatus;
type KindFilter = "all" | InsightKind;

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "new", label: "New" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "dismissed", label: "Dismissed" },
];

const KIND_FILTERS: { value: KindFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "anomaly", label: "Anomaly" },
  { value: "trend", label: "Trend" },
  { value: "opportunity", label: "Opportunity" },
  { value: "decay", label: "Decay" },
  { value: "cannibalization", label: "Cannibalization" },
];

const SEVERITY_ORDER: InsightSeverity[] = ["critical", "high", "medium", "low"];

interface SeverityStyle {
  border: string;
  pillBg: string;
  pillText: string;
  iconText: string;
  label: string;
}

const SEVERITY_STYLES: Record<InsightSeverity, SeverityStyle> = {
  critical: {
    border: "border-l-red-500",
    pillBg: "bg-red-500/15 border-red-500/30",
    pillText: "text-red-400",
    iconText: "text-red-400",
    label: "Critical",
  },
  high: {
    border: "border-l-orange-500",
    pillBg: "bg-orange-500/15 border-orange-500/30",
    pillText: "text-orange-400",
    iconText: "text-orange-400",
    label: "High",
  },
  medium: {
    border: "border-l-amber-500",
    pillBg: "bg-amber-500/15 border-amber-500/30",
    pillText: "text-amber-400",
    iconText: "text-amber-400",
    label: "Medium",
  },
  low: {
    border: "border-l-slate-500",
    pillBg: "bg-slate-700/40 border-slate-600/40",
    pillText: "text-slate-300",
    iconText: "text-slate-400",
    label: "Low",
  },
};

const KIND_LABELS: Record<InsightKind, string> = {
  anomaly: "Anomaly",
  trend: "Trend",
  opportunity: "Opportunity",
  decay: "Decay",
  cannibalization: "Cannibalization",
};

function KindIcon({
  kind,
  className,
}: {
  kind: InsightKind;
  className?: string;
}) {
  switch (kind) {
    case "anomaly":
      return <AlertTriangle className={className} size={18} />;
    case "trend":
      return <TrendingUp className={className} size={18} />;
    case "opportunity":
      return <Target className={className} size={18} />;
    case "decay":
      return <TrendingDown className={className} size={18} />;
    case "cannibalization":
      return <Split className={className} size={18} />;
  }
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function formatPeriod(startISO: string, endISO: string): string {
  const start = new Date(startISO);
  const end = new Date(endISO);
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear();
  const startStr = `${MONTHS[start.getUTCMonth()]} ${start.getUTCDate()}`;
  const endStr = `${MONTHS[end.getUTCMonth()]} ${end.getUTCDate()}, ${end.getUTCFullYear()}`;
  if (!sameYear) {
    return `${startStr}, ${start.getUTCFullYear()} – ${endStr}`;
  }
  return `${startStr} – ${endStr}`;
}

function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, now.getTime() - then);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ${days === 1 ? "day" : "days"} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} ${months === 1 ? "month" : "months"} ago`;
  const years = Math.floor(days / 365);
  return `${years} ${years === 1 ? "year" : "years"} ago`;
}

export default function InsightsPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [generateMessage, setGenerateMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  const queryKey = useMemo(
    () => ["insights", propertyId, statusFilter] as const,
    [propertyId, statusFilter],
  );

  const insightsQuery = useQuery({
    queryKey,
    queryFn: () =>
      insightsApi.list(
        propertyId,
        statusFilter === "all" ? {} : { status: statusFilter },
      ),
    enabled: !!propertyId,
    staleTime: 30_000,
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({
      insightId,
      status,
    }: {
      insightId: number;
      status: Exclude<InsightStatus, "new">;
    }) => insightsApi.updateStatus(propertyId, insightId, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["insights", propertyId],
      });
    },
  });

  const generateMutation = useMutation({
    mutationFn: () => insightsApi.generate(propertyId),
    onSuccess: (data) => {
      setGenerateMessage({
        tone: "success",
        text: `Generated ${data.generated} new insight${data.generated === 1 ? "" : "s"} from ${data.total_anomalies_detected} anomal${data.total_anomalies_detected === 1 ? "y" : "ies"}.`,
      });
      void queryClient.invalidateQueries({
        queryKey: ["insights", propertyId],
      });
    },
    onError: (err: Error) => {
      setGenerateMessage({
        tone: "error",
        text: err.message,
      });
    },
  });

  const allItems = insightsQuery.data?.items ?? [];

  const filteredItems = useMemo(() => {
    if (kindFilter === "all") return allItems;
    return allItems.filter((i) => i.kind === kindFilter);
  }, [allItems, kindFilter]);

  const severityCounts = useMemo(() => {
    const counts: Record<InsightSeverity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
    };
    for (const item of allItems) {
      counts[item.severity] += 1;
    }
    return counts;
  }, [allItems]);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Insights" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm text-slate-400">
                AI-generated observations from your data
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setGenerateMessage(null);
                  generateMutation.mutate();
                }}
                disabled={generateMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {generateMutation.isPending ? (
                  <RefreshCw size={12} className="animate-spin" />
                ) : (
                  <Sparkles size={12} />
                )}
                {generateMutation.isPending
                  ? "Generating…"
                  : "Generate new insights"}
              </button>
              {generateMessage && (
                <div
                  className={clsx(
                    "rounded-md border px-3 py-1.5 text-xs",
                    generateMessage.tone === "success"
                      ? "border-green-500/30 bg-green-500/10 text-green-300"
                      : "border-red-500/30 bg-red-500/10 text-red-300",
                  )}
                >
                  {generateMessage.text}
                </div>
              )}
            </div>
          </div>

          <div className="mb-4 space-y-3">
            <FilterPills
              label="Status"
              options={STATUS_FILTERS}
              active={statusFilter}
              onChange={setStatusFilter}
            />
            <FilterPills
              label="Kind"
              options={KIND_FILTERS}
              active={kindFilter}
              onChange={setKindFilter}
            />
          </div>

          {insightsQuery.data && (
            <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>
                Showing{" "}
                <span className="font-medium text-slate-300">
                  {filteredItems.length}
                </span>{" "}
                of{" "}
                <span className="font-medium text-slate-300">
                  {allItems.length}
                </span>{" "}
                insights
              </span>
              {SEVERITY_ORDER.filter((s) => severityCounts[s] > 0).map((s) => (
                <span
                  key={s}
                  className={clsx(
                    "inline-flex items-center gap-1",
                    SEVERITY_STYLES[s].pillText,
                  )}
                >
                  <span
                    className={clsx(
                      "h-1.5 w-1.5 rounded-full",
                      s === "critical" && "bg-red-500",
                      s === "high" && "bg-orange-500",
                      s === "medium" && "bg-amber-500",
                      s === "low" && "bg-slate-500",
                    )}
                  />
                  {severityCounts[s]} {SEVERITY_STYLES[s].label.toLowerCase()}
                </span>
              ))}
            </div>
          )}

          {insightsQuery.isLoading && <InsightsSkeleton />}

          {insightsQuery.isError && (
            <ErrorBanner
              message={(insightsQuery.error as Error).message}
              onRetry={() => void insightsQuery.refetch()}
              retrying={insightsQuery.isFetching}
            />
          )}

          {insightsQuery.data && filteredItems.length === 0 && (
            <EmptyState />
          )}

          {filteredItems.length > 0 && (
            <div className="space-y-3">
              {filteredItems.map((insight) => (
                <InsightCard
                  key={insight.id}
                  insight={insight}
                  onUpdateStatus={(status) =>
                    updateStatusMutation.mutate({
                      insightId: insight.id,
                      status,
                    })
                  }
                  isUpdating={
                    updateStatusMutation.isPending &&
                    updateStatusMutation.variables?.insightId === insight.id
                  }
                />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

interface FilterPillsProps<T extends string> {
  label: string;
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

function FilterPills<T extends string>({
  label,
  options,
  active,
  onChange,
}: FilterPillsProps<T>) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </span>
      <div className="inline-flex items-center rounded-lg border border-slate-700 bg-slate-900 p-0.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={clsx(
              "rounded-md px-3 py-1 text-xs font-medium transition",
              active === opt.value
                ? "bg-brand-600 text-white"
                : "text-slate-400 hover:text-white",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

interface InsightCardProps {
  insight: InsightResponse;
  onUpdateStatus: (status: Exclude<InsightStatus, "new">) => void;
  isUpdating: boolean;
}

function InsightCard({ insight, onUpdateStatus, isUpdating }: InsightCardProps) {
  const [expanded, setExpanded] = useState(false);
  const sev = SEVERITY_STYLES[insight.severity];

  return (
    <article
      className={clsx(
        "rounded-xl border border-slate-800 border-l-4 bg-slate-900 p-5 transition",
        sev.border,
      )}
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <KindIcon kind={insight.kind} className={sev.iconText} />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            {KIND_LABELS[insight.kind]}
          </span>
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold",
            sev.pillBg,
            sev.pillText,
          )}
        >
          {sev.label}
        </span>
      </div>

      <h3 className="mb-1.5 text-base font-semibold text-white">
        {insight.title}
      </h3>
      <p className="mb-3 text-sm text-slate-300">{insight.summary}</p>

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>
          Period:{" "}
          <span className="text-slate-400">
            {formatPeriod(insight.period_start, insight.period_end)}
          </span>
        </span>
        <span>
          Detected:{" "}
          <span className="text-slate-400">
            {formatRelativeTime(insight.detected_at)}
          </span>
        </span>
      </div>

      <div className="mb-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition hover:text-white"
        >
          {expanded ? (
            <ChevronDown size={12} />
          ) : (
            <ChevronRight size={12} />
          )}
          {expanded ? "Hide supporting data" : "View supporting data"}
        </button>
        {expanded && (
          <pre className="mt-2 max-h-80 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs leading-relaxed text-slate-300">
            <code>{JSON.stringify(insight.supporting_data, null, 2)}</code>
          </pre>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-slate-800 pt-3">
        {insight.status === "new" && (
          <>
            <button
              type="button"
              onClick={() => onUpdateStatus("acknowledged")}
              disabled={isUpdating}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CheckCircle2 size={12} />
              Acknowledge
            </button>
            <button
              type="button"
              onClick={() => onUpdateStatus("dismissed")}
              disabled={isUpdating}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              <XCircle size={12} />
              Dismiss
            </button>
          </>
        )}
        {insight.status === "acknowledged" && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-green-500/30 bg-green-500/10 px-2.5 py-1 text-xs font-medium text-green-300">
            <CheckCircle2 size={12} />
            Acknowledged
          </span>
        )}
        {insight.status === "dismissed" && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800/50 px-2.5 py-1 text-xs font-medium text-slate-400">
            <XCircle size={12} />
            Dismissed
          </span>
        )}
      </div>
    </article>
  );
}

function InsightsSkeleton() {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-xl border border-slate-800 border-l-4 border-l-slate-700 bg-slate-900 p-5"
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="h-3 w-24 rounded bg-slate-800" />
            <div className="h-5 w-16 rounded bg-slate-800" />
          </div>
          <div className="mb-2 h-4 w-2/3 rounded bg-slate-800" />
          <div className="mb-1.5 h-3 w-full rounded bg-slate-800/70" />
          <div className="mb-4 h-3 w-5/6 rounded bg-slate-800/70" />
          <div className="flex gap-2">
            <div className="h-7 w-28 rounded-lg bg-slate-800" />
            <div className="h-7 w-20 rounded-lg bg-slate-800" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800/60 text-brand-500">
        <Lightbulb className="h-6 w-6" />
      </div>
      <h3 className="mb-1 text-sm font-semibold text-white">No insights yet</h3>
      <p className="mx-auto max-w-sm text-xs text-slate-400">
        Click &quot;Generate new insights&quot; to run anomaly detection.
      </p>
    </div>
  );
}

interface ErrorBannerProps {
  message: string;
  onRetry: () => void;
  retrying: boolean;
}

function ErrorBanner({ message, onRetry, retrying }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="mb-6 flex items-start justify-between gap-4 rounded-xl border border-red-900 bg-red-950/60 p-4"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
        <div>
          <p className="text-sm font-semibold text-red-300">
            Failed to load insights
          </p>
          <p className="mt-0.5 text-xs text-red-400/80">{message}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-red-800 bg-red-900/40 px-3 py-1.5 text-xs font-medium text-red-200 transition hover:bg-red-900/70 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RefreshCw className={clsx("h-3 w-3", retrying && "animate-spin")} />
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}
