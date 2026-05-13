"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertCircle,
  ArrowRight,
  BookmarkCheck,
  CheckCircle2,
  Loader2,
  Pin,
  Play,
  Plus,
  RefreshCw,
  Star,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  pinnedApi,
  type PinnedQuestionResponse,
  type PinnedRunResponse,
} from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

type SourceScope = "all" | "ga4" | "gsc";
type DateRangeStrategy = "rolling_7d" | "rolling_28d" | "rolling_90d" | "mtd" | "qtd" | "ytd";

interface NewPinForm {
  title: string;
  prompt: string;
  source_scope: SourceScope;
  date_range_strategy: DateRangeStrategy;
  tags: string;
}

const EMPTY_FORM: NewPinForm = {
  title: "",
  prompt: "",
  source_scope: "all",
  date_range_strategy: "rolling_28d",
  tags: "",
};

const DATE_RANGE_OPTIONS: { value: DateRangeStrategy; label: string }[] = [
  { value: "rolling_7d", label: "Rolling 7 days" },
  { value: "rolling_28d", label: "Rolling 28 days" },
  { value: "rolling_90d", label: "Rolling 90 days" },
  { value: "mtd", label: "Month to date" },
  { value: "qtd", label: "Quarter to date" },
  { value: "ytd", label: "Year to date" },
];

// ── Run status ────────────────────────────────────────────────────────────────

function RunStatusBadge({ run }: { run: PinnedRunResponse | null | undefined }) {
  if (!run) {
    return (
      <span className="text-xs text-slate-600">Never run</span>
    );
  }
  if (run.run_status === "pending") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-yellow-400">
        <Loader2 size={10} className="animate-spin" />
        Running
      </span>
    );
  }
  if (run.run_status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-400">
        <AlertCircle size={10} />
        Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-green-400">
      <CheckCircle2 size={10} />
      Done &middot; {new Date(run.run_at).toLocaleDateString()}
    </span>
  );
}

function DiffDirectionIcon({ run }: { run: PinnedRunResponse | null | undefined }) {
  if (!run?.answer_json) return null;
  try {
    const parsed = JSON.parse(run.answer_json) as { diff_direction?: string };
    const dir = parsed.diff_direction;
    if (dir === "improved") return <TrendingUp size={14} className="text-green-400" />;
    if (dir === "worsened") return <TrendingDown size={14} className="text-red-400" />;
    if (dir === "stable") return <span className="text-sm text-slate-400">→</span>;
    if (dir === "mixed") return <span className="text-sm text-slate-400">~</span>;
    if (dir === "new_signal") return <Star size={14} className="text-amber-400" />;
  } catch {
    // ignore
  }
  return null;
}

// ── Pin card ──────────────────────────────────────────────────────────────────

interface PinCardProps {
  pin: PinnedQuestionResponse;
  propertyId: number;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
  isRunning: boolean;
  isDeleting: boolean;
}

function PinCard({ pin, propertyId, onRun, onDelete, isRunning, isDeleting }: PinCardProps) {
  const run = pin.latest_run ?? null;

  return (
    <article className="flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">{pin.title}</h3>
        <div className="flex flex-shrink-0 items-center gap-1">
          <DiffDirectionIcon run={run} />
          <button
            type="button"
            onClick={() => onDelete(pin.id)}
            disabled={isDeleting}
            title="Delete pin"
            className="rounded p-0.5 text-slate-600 hover:text-red-400 transition disabled:opacity-40"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <p className="mb-3 line-clamp-2 text-xs text-slate-400">{pin.prompt}</p>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-300 uppercase">
          {pin.source_scope}
        </span>
        <span className="rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
          {DATE_RANGE_OPTIONS.find((o) => o.value === pin.date_range_strategy)?.label ??
            pin.date_range_strategy}
        </span>
        {(pin.tags ?? []).map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-slate-700/50 bg-slate-800/50 px-2 py-0.5 text-[10px] text-slate-500"
          >
            {tag}
          </span>
        ))}
      </div>

      <div className="mb-4 flex items-center gap-2">
        <RunStatusBadge run={run} />
      </div>

      <div className="mt-auto flex items-center gap-2 border-t border-slate-800 pt-3">
        <button
          type="button"
          onClick={() => onRun(pin.id)}
          disabled={isRunning}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRunning ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Play size={11} />
          )}
          {isRunning ? "Running…" : "Re-run"}
        </button>
        <Link
          href={`/pinned/${pin.id}?property_id=${propertyId}` as Route}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 hover:border-slate-600 hover:text-white transition"
        >
          Open
          <ArrowRight size={11} />
        </Link>
      </div>
    </article>
  );
}

// ── New pin modal ─────────────────────────────────────────────────────────────

interface NewPinModalProps {
  onClose: () => void;
  onSave: (form: NewPinForm) => void;
  saving: boolean;
}

function NewPinModal({ onClose, onSave, saving }: NewPinModalProps) {
  const [form, setForm] = useState<NewPinForm>(EMPTY_FORM);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.prompt.trim()) return;
    onSave(form);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-base font-semibold text-white">New pinned question</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:text-white transition"
          >
            <X size={16} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Title
            </label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Weekly brand click share"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Prompt
            </label>
            <textarea
              value={form.prompt}
              onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
              placeholder="What question should Claude answer each time?"
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Source scope
              </label>
              <select
                value={form.source_scope}
                onChange={(e) =>
                  setForm((f) => ({ ...f, source_scope: e.target.value as SourceScope }))
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-slate-500 focus:outline-none"
              >
                <option value="all">All</option>
                <option value="ga4">GA4</option>
                <option value="gsc">GSC</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Date range
              </label>
              <select
                value={form.date_range_strategy}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    date_range_strategy: e.target.value as DateRangeStrategy,
                  }))
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-slate-500 focus:outline-none"
              >
                {DATE_RANGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Tags{" "}
              <span className="font-normal text-slate-600">(comma-separated)</span>
            </label>
            <input
              type="text"
              value={form.tags}
              onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              placeholder="seo, brand, weekly"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
            />
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-slate-800 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-400 hover:border-slate-600 hover:text-white transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !form.title.trim() || !form.prompt.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Pin size={13} />
              )}
              {saving ? "Saving…" : "Save pin"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PinnedPage() {
  const searchParams = useSearchParams();
  const propertyId = Number(searchParams.get("property_id") ?? 0);
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);

  const pinsQuery = useQuery({
    queryKey: ["pinned", propertyId],
    queryFn: () => pinnedApi.list(propertyId),
    enabled: !!propertyId,
    staleTime: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: (id: number) => pinnedApi.run(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pinned", propertyId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => pinnedApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pinned", propertyId] });
    },
  });

  const createMutation = useMutation({
    mutationFn: (form: NewPinForm) =>
      pinnedApi.create({
        property_id: propertyId,
        title: form.title,
        prompt: form.prompt,
        source_scope: form.source_scope,
        date_range_strategy: form.date_range_strategy,
        tags: form.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      setShowModal(false);
      void queryClient.invalidateQueries({ queryKey: ["pinned", propertyId] });
    },
  });

  const pins = pinsQuery.data ?? [];

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Pinned Questions" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          {/* Top bar */}
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400">
                Track questions over time &mdash; Claude re-runs them on demand.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowModal(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-brand-700"
            >
              <Plus size={13} />
              New pin
            </button>
          </div>

          {/* Error */}
          {pinsQuery.isError && (
            <div
              role="alert"
              className="mb-6 flex items-start gap-3 rounded-xl border border-red-900 bg-red-950/60 p-4"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
              <div>
                <p className="text-sm font-semibold text-red-300">Failed to load pinned questions</p>
                <p className="mt-0.5 text-xs text-red-400/80">
                  {(pinsQuery.error as Error).message}
                </p>
              </div>
            </div>
          )}

          {/* Loading */}
          {pinsQuery.isLoading && (
            <div className="grid gap-4 md:grid-cols-2 animate-pulse">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-48 rounded-xl border border-slate-800 bg-slate-900"
                />
              ))}
            </div>
          )}

          {/* Empty */}
          {!pinsQuery.isLoading && pins.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800/60 text-brand-500">
                <BookmarkCheck className="h-6 w-6" />
              </div>
              <h3 className="mb-1 text-sm font-semibold text-white">No pinned questions yet</h3>
              <p className="mx-auto max-w-sm text-xs text-slate-400">
                Pin questions from the chat to track them over time.
              </p>
            </div>
          )}

          {/* Grid */}
          {pins.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {pins.map((pin) => (
                <PinCard
                  key={pin.id}
                  pin={pin}
                  propertyId={propertyId}
                  onRun={(id) => runMutation.mutate(id)}
                  onDelete={(id) => deleteMutation.mutate(id)}
                  isRunning={
                    runMutation.isPending &&
                    (runMutation.variables as number) === pin.id
                  }
                  isDeleting={
                    deleteMutation.isPending &&
                    (deleteMutation.variables as number) === pin.id
                  }
                />
              ))}
            </div>
          )}
        </main>
      </div>

      {showModal && (
        <NewPinModal
          onClose={() => setShowModal(false)}
          onSave={(form) => createMutation.mutate(form)}
          saving={createMutation.isPending}
        />
      )}
    </div>
  );
}
