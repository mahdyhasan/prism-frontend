"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertCircle,
  ArrowRight,
  Eye,
  Lightbulb,
  RefreshCw,
  TrendingUp,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  briefApi,
  type DailyBriefResponse,
  type BriefNotReadyResponse,
} from "@/lib/api-client";

// ── Brief JSON shape ──────────────────────────────────────────────────────────

type Confidence =
  | "high"
  | "medium"
  | "hypothesis"
  | "speculation"
  | "insufficient_data";

interface BriefFinding {
  text: string;
  confidence: Confidence;
  evidence_ref?: string;
  drill_into?: string;
}

interface BriefReconsider {
  challenge: string;
  rationale: string;
  confidence: Confidence;
}

interface BriefWatching {
  signal: string;
  reason_to_watch: string;
}

interface BriefJson {
  headline: string;
  date_label?: string;
  headline_confidence?: Confidence;
  continuity_note?: string | null;
  /** Claude outputs this field as "bullets" (matches daily_brief.md schema) */
  bullets?: BriefFinding[];
  reconsider?: BriefReconsider[];
  watching?: BriefWatching[];
}

// ── Confidence chip ──────────────────────────────────────────────────────────

const CONFIDENCE_STYLES: Record<Confidence, { bg: string; text: string; label: string }> = {
  high: { bg: "bg-green-950/60 border-green-500/30", text: "text-green-400", label: "high" },
  medium: { bg: "bg-yellow-950/60 border-yellow-500/30", text: "text-yellow-400", label: "medium" },
  hypothesis: { bg: "bg-purple-950/60 border-purple-500/30", text: "text-purple-400", label: "hypothesis" },
  speculation: { bg: "bg-slate-800 border-slate-600/30", text: "text-slate-400", label: "speculation" },
  insufficient_data: { bg: "bg-slate-800 border-slate-600/30", text: "text-slate-500", label: "insufficient data" },
};

function ConfidenceChip({ confidence }: { confidence: Confidence }) {
  const s = CONFIDENCE_STYLES[confidence] ?? CONFIDENCE_STYLES.speculation;
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        s.bg,
        s.text,
      )}
    >
      {s.label}
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BriefPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const queryClient = useQueryClient();
  // True from the moment "Generate now" fires until the brief lands (or errors).
  const [awaitingGeneration, setAwaitingGeneration] = useState(false);
  const generatingUntil = useRef<number>(0);

  const briefQuery = useQuery({
    queryKey: ["brief", propertyId],
    queryFn: () => briefApi.get(propertyId),
    enabled: !!propertyId,
    staleTime: 5_000,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const isWaiting =
        ("status" in data && (data.status === "not_ready" || data.status === "error")) ||
        ("brief_json" in data && (data as DailyBriefResponse).brief_json === null);
      if (!isWaiting) return false;
      // Poll every 5 s for 90 s after triggering generation, then fall back to 30 s.
      return Date.now() < generatingUntil.current ? 5_000 : 30_000;
    },
  });

  const data = briefQuery.data;

  // Clear awaitingGeneration once the brief arrives or an error is surfaced.
  useEffect(() => {
    if (!awaitingGeneration || !data) return;
    const briefIsReady =
      "brief_json" in data && (data as DailyBriefResponse).brief_json !== null;
    const isError =
      "status" in data && (data as BriefNotReadyResponse).status === "error";
    if (briefIsReady || isError) {
      setAwaitingGeneration(false);
    }
  }, [data, awaitingGeneration]);

  const regenerateMutation = useMutation({
    mutationFn: () => briefApi.regenerate(propertyId),
    onSuccess: () => {
      setAwaitingGeneration(true);
      generatingUntil.current = Date.now() + 90_000; // fast-poll window
      void queryClient.invalidateQueries({ queryKey: ["brief", propertyId] });
    },
  });

  const isNotReady =
    !data ||
    ("status" in data &&
      (data.status === "not_ready" || data.status === "error")) ||
    ("brief_json" in data && (data as DailyBriefResponse).brief_json === null);

  const brief =
    data && "brief_json" in data && (data as DailyBriefResponse).brief_json
      ? (JSON.parse((data as DailyBriefResponse).brief_json!) as BriefJson)
      : null;

  const generationCount =
    data && "generation_count" in data ? (data as DailyBriefResponse).generation_count : 0;

  const canRegenerate = generationCount < 3;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Daily Brief" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">

          {briefQuery.isError && (
            <div
              role="alert"
              className="mb-6 flex items-start gap-3 rounded-xl border border-red-900 bg-red-950/60 p-4"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
              <div>
                <p className="text-sm font-semibold text-red-300">Failed to load brief</p>
                <p className="mt-0.5 text-xs text-red-400/80">
                  {(briefQuery.error as Error).message}
                </p>
              </div>
            </div>
          )}

          {briefQuery.isLoading && <BriefSkeleton />}

          {!briefQuery.isLoading && isNotReady && (
            <NotReadyState
              status={
                data && "status" in data
                  ? (data as BriefNotReadyResponse).status
                  : "not_ready"
              }
              message={
                data && "message" in data
                  ? (data as BriefNotReadyResponse).message
                  : "Your brief will be ready after the morning data sync."
              }
              generating={awaitingGeneration || regenerateMutation.isPending}
              onRegenerate={() => regenerateMutation.mutate()}
              regenerating={regenerateMutation.isPending}
              canRegenerate={canRegenerate}
            />
          )}

          {brief && data && "id" in data && (
            <BriefContent
              brief={brief}
              briefData={data as DailyBriefResponse}
              propertyId={propertyId}
              onRegenerate={() => regenerateMutation.mutate()}
              regenerating={regenerateMutation.isPending}
              canRegenerate={canRegenerate}
            />
          )}
        </main>
      </div>
    </div>
  );
}

// ── Not-ready state ───────────────────────────────────────────────────────────

interface NotReadyStateProps {
  status: string;
  message: string;
  generating: boolean;
  onRegenerate: () => void;
  regenerating: boolean;
  canRegenerate: boolean;
}

function NotReadyState({ status, message, generating, onRegenerate, regenerating, canRegenerate }: NotReadyStateProps) {
  const isError = status === "error";
  const isGenerating = generating || regenerating;

  return (
    <div className="flex min-h-[420px] items-center justify-center">
      <div className={clsx(
        "max-w-md rounded-2xl border p-8 text-center",
        isError
          ? "border-red-900/60 bg-red-950/20"
          : "border-slate-800 bg-slate-900",
      )}>
        <div className={clsx(
          "mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full",
          isError ? "bg-red-900/40 text-red-400" : "bg-slate-800/60 text-brand-500",
        )}>
          {isError ? <AlertCircle className="h-6 w-6" /> : <Lightbulb className="h-6 w-6" />}
        </div>

        <h3 className="mb-2 text-base font-semibold text-white">
          {isGenerating && !isError ? "Generating your brief…" : isError ? "Generation failed" : "Brief not ready yet"}
        </h3>

        {isGenerating && !isError ? (
          <p className="mb-6 text-sm text-slate-400">
            Claude is analysing your analytics data. This usually takes 15–30 seconds.
          </p>
        ) : (
          <p className={clsx("mb-6 text-sm", isError ? "text-red-400/80" : "text-slate-400")}>
            {message}
          </p>
        )}

        {!isGenerating && canRegenerate && (
          <button
            type="button"
            onClick={onRegenerate}
            disabled={regenerating}
            className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={14} className={regenerating ? "animate-spin" : ""} />
            {isError ? "Retry generation" : "Generate now"}
          </button>
        )}
        {isGenerating && (
          <div className="flex justify-center">
            <RefreshCw size={18} className="animate-spin text-brand-500" />
          </div>
        )}
        {!isGenerating && !canRegenerate && (
          <p className="text-xs text-slate-500">Daily regeneration limit (3) reached.</p>
        )}
      </div>
    </div>
  );
}

// ── Brief content ─────────────────────────────────────────────────────────────

interface BriefContentProps {
  brief: BriefJson;
  briefData: DailyBriefResponse;
  propertyId: number;
  onRegenerate: () => void;
  regenerating: boolean;
  canRegenerate: boolean;
}

function BriefContent({
  brief,
  briefData,
  propertyId,
  onRegenerate,
  regenerating,
  canRegenerate,
}: BriefContentProps) {
  const drillLink = useCallback(
    (drillInto: string) =>
      `/chat?property_id=${propertyId}&prompt=${encodeURIComponent(drillInto)}`,
    [propertyId],
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Continuity note */}
      {brief.continuity_note && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 px-4 py-3 text-sm text-slate-400">
          {brief.continuity_note}
        </div>
      )}

      {/* Hero */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {brief.date_label && (
            <span className="rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-300">
              {brief.date_label}
            </span>
          )}
          {brief.headline_confidence && (
            <ConfidenceChip confidence={brief.headline_confidence} />
          )}
          <div className="ml-auto flex items-center gap-2">
            {canRegenerate ? (
              <button
                type="button"
                onClick={onRegenerate}
                disabled={regenerating}
                title={`${briefData.generation_count}/3 regenerations used today`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 hover:border-slate-600 hover:text-white transition disabled:opacity-50"
              >
                <RefreshCw size={11} className={regenerating ? "animate-spin" : ""} />
                {regenerating ? "Refreshing…" : `Refresh brief (${briefData.generation_count}/3)`}
              </button>
            ) : (
              <span className="text-xs text-slate-500">Limit reached (3/3 today)</span>
            )}
          </div>
        </div>
        <h1 className="text-xl font-bold leading-snug text-white">{brief.headline}</h1>
        <p className="mt-2 text-xs text-slate-500">
          Generated {new Date(briefData.generated_at).toLocaleString()}
        </p>
      </div>

      {/* Bullets / Findings */}
      {brief.bullets && brief.bullets.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
            <TrendingUp size={13} />
            Findings
          </h2>
          <div className="space-y-2">
            {brief.bullets.map((finding, i) => (
              <div
                key={i}
                className="flex items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4"
              >
                <div className="flex-1 space-y-1.5">
                  <p className="text-sm text-slate-200">{finding.text}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <ConfidenceChip confidence={finding.confidence} />
                    {finding.evidence_ref && (
                      <span className="text-xs text-slate-500">{finding.evidence_ref}</span>
                    )}
                  </div>
                </div>
                {finding.drill_into && (
                  <Link
                    href={drillLink(finding.drill_into) as Route}
                    title={finding.drill_into}
                    className="flex-shrink-0 inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs font-medium text-slate-400 hover:border-brand-600 hover:text-brand-400 transition"
                  >
                    Ask
                    <ArrowRight size={11} />
                  </Link>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Reconsider */}
      {brief.reconsider && brief.reconsider.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
            <AlertCircle size={13} />
            What I&apos;d reconsider
          </h2>
          <div className="space-y-2">
            {brief.reconsider.map((item, i) => (
              <div
                key={i}
                className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-4"
              >
                <div className="mb-1.5 flex items-center gap-2">
                  <p className="text-sm font-medium text-amber-200">{item.challenge}</p>
                  <ConfidenceChip confidence={item.confidence} />
                </div>
                <p className="text-xs text-slate-400">{item.rationale}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Watching */}
      {brief.watching && brief.watching.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
            <Eye size={13} />
            Watching
          </h2>
          <div className="space-y-2">
            {brief.watching.map((item, i) => (
              <div
                key={i}
                className="rounded-xl border border-slate-800 bg-slate-900 p-4"
              >
                <p className="mb-1 text-sm font-medium text-white">{item.signal}</p>
                <p className="text-xs text-slate-400">{item.reason_to_watch}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function BriefSkeleton() {
  return (
    <div className="mx-auto max-w-3xl animate-pulse space-y-6" aria-hidden>
      <div className="h-32 rounded-2xl border border-slate-800 bg-slate-900" />
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl border border-slate-800 bg-slate-900" />
        ))}
      </div>
    </div>
  );
}
