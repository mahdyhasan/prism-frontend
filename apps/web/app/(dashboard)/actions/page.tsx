"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  XCircle,
  Zap,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  actionsApi,
  type ActionResponse,
  type ActionStatus,
} from "@/lib/api-client";

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  ActionStatus,
  { label: string; icon: React.ElementType; color: string }
> = {
  pending_confirmation: {
    label: "Awaiting confirmation",
    icon: Clock,
    color: "text-amber-400",
  },
  confirmed: { label: "Confirmed", icon: CheckCircle2, color: "text-brand-400" },
  executing: { label: "Executing", icon: Loader2, color: "text-brand-400" },
  succeeded: { label: "Succeeded", icon: CheckCircle2, color: "text-emerald-400" },
  failed: { label: "Failed", icon: XCircle, color: "text-red-400" },
  cancelled: { label: "Cancelled", icon: XCircle, color: "text-slate-500" },
  expired: { label: "Expired", icon: Clock, color: "text-slate-500" },
};

const TOOL_LABELS: Record<string, string> = {
  gsc_submit_sitemap: "Submit sitemap",
  gsc_delete_sitemap: "Delete sitemap",
  gsc_inspect_url: "Inspect URL",
  run_psi_audit: "PSI audit",
};

// ── Filter chips ──────────────────────────────────────────────────────────────

type FilterChip = "all" | "pending_confirmation" | "succeeded" | "failed";

const FILTER_CHIPS: { value: FilterChip; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pending_confirmation", label: "Pending" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
];

// ── Action card ───────────────────────────────────────────────────────────────

function ActionCard({
  action,
  propertyId,
}: {
  action: ActionResponse;
  propertyId: number;
}) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const confirmMut = useMutation({
    mutationFn: () => {
      if (!action.confirmation_token) throw new Error("No confirmation token");
      return actionsApi.confirm(action.id, action.confirmation_token);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["actions", propertyId] });
    },
  });

  const cancelMut = useMutation({
    mutationFn: () => actionsApi.cancel(action.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["actions", propertyId] });
    },
  });

  const cfg = STATUS_CONFIG[action.status];
  const StatusIcon = cfg.icon;
  const isPending = action.status === "pending_confirmation";
  const isDestructive = action.tool_name === "gsc_delete_sitemap";

  return (
    <div
      className={clsx(
        "rounded-xl border bg-slate-900 transition",
        isPending ? "border-amber-500/40" : "border-slate-800",
      )}
    >
      <button
        className="flex w-full items-start gap-4 px-5 py-4 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <StatusIcon
          size={18}
          className={clsx("mt-0.5 shrink-0", cfg.color, action.status === "executing" && "animate-spin")}
        />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-white">
              {TOOL_LABELS[action.tool_name] ?? action.tool_name}
            </span>
            {isDestructive && (
              <span className="flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-1.5 py-0.5 text-xs font-medium text-red-400">
                <AlertTriangle size={10} />
                Destructive
              </span>
            )}
            <span className={clsx("text-xs font-medium", cfg.color)}>{cfg.label}</span>
          </div>
          <p className="mt-0.5 truncate font-mono text-xs text-slate-400">
            {JSON.stringify(action.tool_input)}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {new Date(action.created_at).toLocaleString()}
          </p>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-800 px-5 py-4 space-y-3">
          <div className="rounded-lg bg-slate-800/50 p-3 font-mono text-xs text-slate-300">
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(action.tool_input, null, 2)}
            </pre>
          </div>
          {action.result && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">Result</p>
              <div className="rounded-lg bg-slate-800/50 p-3 font-mono text-xs text-emerald-300">
                <pre className="whitespace-pre-wrap break-all">
                  {JSON.stringify(action.result, null, 2)}
                </pre>
              </div>
            </div>
          )}
          {action.error && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">Error</p>
              <p className="rounded-lg bg-red-900/20 p-3 text-xs text-red-400">
                {action.error}
              </p>
            </div>
          )}
        </div>
      )}

      {isPending && (
        <div className="flex items-center gap-3 border-t border-slate-800 px-5 py-3">
          {isDestructive && (
            <p className="flex-1 text-xs text-red-400">
              This will permanently delete the sitemap from Google Search Console.
            </p>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white transition disabled:opacity-50"
            >
              {cancelMut.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                "Cancel"
              )}
            </button>
            <button
              onClick={() => confirmMut.mutate()}
              disabled={confirmMut.isPending || !action.confirmation_token}
              className={clsx(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:opacity-50",
                isDestructive
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "bg-brand-600 text-white hover:bg-brand-700",
              )}
            >
              {confirmMut.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : isDestructive ? (
                "Confirm — delete"
              ) : (
                "Confirm"
              )}
            </button>
          </div>
          {confirmMut.isError && (
            <p className="mt-1 w-full text-xs text-red-400">
              {(confirmMut.error as Error).message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Inner page (needs useSearchParams inside Suspense) ────────────────────────

function ActionsInner() {
  const searchParams = useSearchParams();
  const propertyId = Number(searchParams.get("property_id") ?? "0");
  const [filter, setFilter] = useState<FilterChip>("all");

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["actions", propertyId],
    queryFn: () =>
      actionsApi.list(propertyId, { limit: 100 }),
    staleTime: 30 * 1000,
    enabled: propertyId > 0,
    refetchInterval: 15 * 1000, // Poll for executing actions
  });

  const actions = (data ?? []).filter((a) =>
    filter === "all" ? true : a.status === filter,
  );

  const pendingCount = (data ?? []).filter(
    (a) => a.status === "pending_confirmation",
  ).length;

  return (
    <div className="flex h-screen bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header propertyId={propertyId} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="flex items-center gap-2 text-xl font-bold text-white">
                  <Zap size={20} className="text-brand-400" />
                  Actions
                  {pendingCount > 0 && (
                    <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
                      {pendingCount} pending
                    </span>
                  )}
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  Actions queued by the AI analyst. Confirm or cancel before they execute.
                </p>
              </div>
              <button
                onClick={() => refetch()}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-white transition"
              >
                <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
                Refresh
              </button>
            </div>

            {/* Filter chips */}
            <div className="flex flex-wrap gap-2">
              {FILTER_CHIPS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={clsx(
                    "rounded-full border px-3 py-1 text-xs font-medium transition",
                    filter === value
                      ? "border-brand-500 bg-brand-500/20 text-brand-300"
                      : "border-slate-700 text-slate-400 hover:text-white",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Content */}
            {!propertyId && (
              <p className="text-sm text-slate-500">No property selected.</p>
            )}
            {isLoading && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 size={14} className="animate-spin" />
                Loading actions...
              </div>
            )}
            {error && (
              <p className="text-sm text-red-400">Failed to load actions.</p>
            )}
            {!isLoading && propertyId > 0 && actions.length === 0 && (
              <div className="rounded-xl border border-slate-800 bg-slate-900 px-5 py-10 text-center">
                <Zap size={32} className="mx-auto mb-2 text-slate-700" />
                <p className="text-sm font-medium text-white">No actions</p>
                <p className="mt-1 text-xs text-slate-500">
                  When the AI analyst queues an action (like submitting a sitemap) it
                  will appear here for your approval.
                </p>
              </div>
            )}
            <div className="space-y-3">
              {actions.map((action) => (
                <ActionCard
                  key={action.id}
                  action={action}
                  propertyId={propertyId}
                />
              ))}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// ── Page export (Suspense boundary for useSearchParams) ───────────────────────

export default function ActionsPage() {
  return (
    <Suspense fallback={null}>
      <ActionsInner />
    </Suspense>
  );
}
