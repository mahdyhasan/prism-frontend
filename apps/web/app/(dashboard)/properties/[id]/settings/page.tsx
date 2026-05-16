"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { signIn } from "next-auth/react";
import { clsx } from "clsx";
import {
  AlertCircle,
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Gauge,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Target,
  Unlink,
  WifiOff,
  X,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  authApi,
  propertiesApi,
  propertySettingsApi,
  syncApi,
  type GA4PropertyOption,
  type GSCSiteOption,
  type IntegrationSyncStatus,
  type PropertyResponse,
  type PropertySettingsResponse,
  type PropertySettingsUpdate,
} from "@/lib/api-client";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const queryClient = useQueryClient();

  const { data: property, isLoading } = useQuery({
    queryKey: ["property", propertyId],
    queryFn: () => propertiesApi.get(propertyId),
    enabled: !!propertyId,
    staleTime: 30_000,
  });

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me(),
    staleTime: 60_000,
  });

  const { data: syncStatus, refetch: refetchSyncStatus } = useQuery({
    queryKey: ["sync-status", propertyId],
    queryFn: () => propertiesApi.getSyncStatus(propertyId),
    enabled: !!propertyId,
    staleTime: 10_000,
    refetchInterval: 20_000,
  });

  const invalidateProperty = () =>
    queryClient.invalidateQueries({ queryKey: ["property", propertyId] });

  const handleSyncDone = () => {
    refetchSyncStatus();
    invalidateProperty();
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Settings" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-2xl space-y-6">
            {isLoading && <SettingsSkeleton />}

            {property && (
              <>
                <PropertyInfoCard property={property} />

                {me && !me.has_google_linked && <ConnectGoogleCard />}

                <GA4Card
                  propertyId={propertyId}
                  property={property}
                  syncStatus={syncStatus?.ga4 ?? null}
                  onSaved={invalidateProperty}
                  onSyncDone={handleSyncDone}
                />

                <GSCCard
                  propertyId={propertyId}
                  property={property}
                  syncStatus={syncStatus?.gsc ?? null}
                  onSaved={invalidateProperty}
                  onSyncDone={handleSyncDone}
                />

                <ConversionEventsCard
                  propertyId={propertyId}
                  property={property}
                  onSaved={invalidateProperty}
                />

                <ClarityCard
                  propertyId={propertyId}
                  property={property}
                  onSaved={invalidateProperty}
                />

                <CWVSettingsCard propertyId={propertyId} />

                <LLMConfigCard propertyId={propertyId} />
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

// ── Connect Google Account ─────────────────────────────────────────────────────

function ConnectGoogleCard() {
  const [loading, setLoading] = useState(false);

  function handleConnect() {
    setLoading(true);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("prism_link_google", "true");
    }
    signIn("google", { callbackUrl: "/login" });
  }

  return (
    <div className="rounded-2xl border border-amber-800/40 bg-amber-950/20 p-6">
      <div className="flex items-start gap-4">
        <div className="mt-0.5 flex-shrink-0 rounded-xl bg-amber-900/40 p-2.5">
          <WifiOff size={18} className="text-amber-400" />
        </div>
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-amber-300">
            Google account not connected
          </h2>
          <p className="mt-1 text-xs text-amber-400/70">
            GA4 and Search Console syncs require a linked Google account. Connect
            yours to enable data pulls.
          </p>
          <button
            onClick={handleConnect}
            disabled={loading}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-amber-500 disabled:opacity-60"
          >
            {loading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <GoogleIcon size={14} />
            )}
            Connect Google Account
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Sync button ────────────────────────────────────────────────────────────────

function SyncButton({
  propertyId,
  source,
  initialStatus,
  onDone,
}: {
  propertyId: number;
  source: "ga4" | "gsc";
  initialStatus: IntegrationSyncStatus | null;
  onDone: () => void;
}) {
  const alreadyRunning =
    initialStatus?.status === "running" || initialStatus?.status === "pending";

  const [activeJobId, setActiveJobId] = useState<number | null>(
    alreadyRunning ? (initialStatus?.job_id ?? null) : null,
  );
  const [jobFinished, setJobFinished] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  // Poll the active job
  const { data: liveJob } = useQuery({
    queryKey: ["sync-job", activeJobId],
    queryFn: () => syncApi.getJob(activeJobId!),
    enabled: !!activeJobId && !jobFinished,
    refetchInterval: 3_000,
    staleTime: 0,
  });

  // When job completes, stop polling and notify parent
  useEffect(() => {
    if (!liveJob) return;
    if (liveJob.status === "done" || liveJob.status === "failed") {
      setJobFinished(true);
      setActiveJobId(null);
      onDoneRef.current();
    }
  }, [liveJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const triggerMutation = useMutation({
    mutationFn: () => propertiesApi.triggerSync(propertyId, source),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      setJobFinished(false);
      setTriggerError(null);
    },
    onError: (err: Error) => setTriggerError(err.message),
  });

  const isRunning =
    triggerMutation.isPending ||
    (!!activeJobId && !jobFinished) ||
    (liveJob?.status === "running" || liveJob?.status === "pending");

  // Determine what to show
  const finishedJob = jobFinished ? liveJob : null;
  const effectiveError =
    finishedJob?.status === "failed"
      ? finishedJob.error
      : !jobFinished && initialStatus?.status === "failed"
        ? initialStatus.error
        : null;

  const lastFinishedAt =
    finishedJob?.finished_at ??
    (!isRunning ? initialStatus?.last_finished_at : null);

  const neverSynced =
    !isRunning &&
    !effectiveError &&
    !initialStatus?.status &&
    !finishedJob;

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={() => triggerMutation.mutate()}
        disabled={isRunning}
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
          isRunning
            ? "cursor-not-allowed border-slate-700 bg-slate-800/60 text-slate-500"
            : effectiveError
              ? "border-red-700/50 bg-red-950/30 text-red-400 hover:bg-red-950/50"
              : neverSynced
                ? "border-brand-700/60 bg-brand-950/20 text-brand-400 hover:bg-brand-950/40"
                : "border-slate-700 text-slate-400 hover:border-slate-600 hover:text-white",
        )}
      >
        {isRunning ? (
          <>
            <Loader2 size={11} className="animate-spin" />
            Syncing…
          </>
        ) : effectiveError ? (
          <>
            <AlertCircle size={11} />
            Sync failed · Retry
          </>
        ) : neverSynced ? (
          <>
            <RefreshCw size={11} />
            No data — Sync now
          </>
        ) : (
          <>
            <RefreshCw size={11} />
            {lastFinishedAt
              ? `Synced ${timeAgo(lastFinishedAt)} · Sync now`
              : "Sync now"}
          </>
        )}
      </button>

      {effectiveError && (
        <p className="text-xs text-red-400 leading-snug">{effectiveError}</p>
      )}
      {triggerError && (
        <p className="text-xs text-red-400 leading-snug">{triggerError}</p>
      )}
    </div>
  );
}

// ── GA4 card ──────────────────────────────────────────────────────────────────

function GA4Card({
  propertyId,
  property,
  syncStatus,
  onSaved,
  onSyncDone,
}: {
  propertyId: number;
  property: PropertyResponse;
  syncStatus: IntegrationSyncStatus | null;
  onSaved: () => void;
  onSyncDone: () => void;
}) {
  const [inputValue, setInputValue] = useState("");
  const [showLinkForm, setShowLinkForm] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  const linked = !!property.ga4_property_id;
  const displayId = property.ga4_property_id?.replace("properties/", "") ?? "";

  const linkMutation = useMutation({
    mutationFn: (ga4Id: string) => propertiesApi.linkGA4(propertyId, ga4Id),
    onSuccess: () => {
      onSaved();
      setShowLinkForm(false);
      setShowPicker(false);
      setInputValue("");
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: () => propertiesApi.unlinkGA4(propertyId),
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-lg text-sm font-black",
              linked ? "bg-orange-500/15 text-orange-400" : "bg-slate-800 text-slate-500",
            )}
          >
            G
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Google Analytics 4</h2>
            <p className="text-xs text-slate-500">Traffic, sessions, revenue</p>
          </div>
        </div>
        <StatusBadge linked={linked} />
      </div>

      {/* Connected state */}
      {linked && !showLinkForm && (
        <>
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-slate-500">Property ID</p>
              <p className="truncate font-mono text-sm text-slate-200">
                properties/{displayId}
              </p>
            </div>
            <a
              href={`https://analytics.google.com/analytics/web/#/p${displayId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 text-brand-500 hover:text-brand-400 transition"
            >
              <ExternalLink size={14} />
            </a>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <SyncButton
              propertyId={propertyId}
              source="ga4"
              initialStatus={syncStatus}
              onDone={onSyncDone}
            />
            <div className="flex-1" />
            <button
              onClick={() => setShowPicker(true)}
              className="text-xs text-slate-600 hover:text-slate-400 transition"
            >
              Change
            </button>
            <button
              onClick={() => unlinkMutation.mutate()}
              disabled={unlinkMutation.isPending}
              className="inline-flex items-center gap-1 rounded-lg border border-red-900/40 bg-red-950/20 px-2.5 py-1.5 text-xs font-medium text-red-400 transition hover:bg-red-950/40 disabled:opacity-50"
            >
              {unlinkMutation.isPending ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <Unlink size={11} />
              )}
              Disconnect
            </button>
          </div>

          {unlinkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(unlinkMutation.error as Error).message}
            </p>
          )}
        </>
      )}

      {/* Disconnected: primary CTA is the Google picker; manual ID is a fallback */}
      {!linked && !showLinkForm && (
        <>
          <button
            onClick={() => setShowPicker(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            <GoogleIcon size={14} /> Choose a GA4 property
          </button>
          <button
            type="button"
            onClick={() => setShowLinkForm(true)}
            className="mt-2 w-full text-center text-xs text-slate-600 hover:text-slate-400 transition"
          >
            Or enter Property ID manually
          </button>
          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}
        </>
      )}

      {/* Manual entry form (fallback) */}
      {(!linked && showLinkForm) && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              linkMutation.mutate(inputValue.trim());
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="123456789  (numeric Property ID)"
              autoFocus
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || linkMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {linkMutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Save size={13} />
              )}
              Link
            </button>
            <button
              type="button"
              onClick={() => {
                setShowLinkForm(false);
                setInputValue("");
              }}
              className="rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-500 hover:text-slate-300 transition"
            >
              Cancel
            </button>
          </form>

          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}

          <p className="mt-3 text-xs text-slate-600">
            Find your numeric Property ID in GA4 → Admin → Property Settings.
            Enter digits only (e.g.{" "}
            <span className="font-mono text-slate-500">123456789</span>).
          </p>
        </>
      )}

      {/* Picker modal — used both for initial connect and for "Change" */}
      {showPicker && (
        <GooglePickerModal
          kind="ga4"
          currentValue={property.ga4_property_id ?? null}
          onClose={() => setShowPicker(false)}
          onSelect={(value) => linkMutation.mutate(value)}
          submitting={linkMutation.isPending}
          submitError={
            linkMutation.isError ? (linkMutation.error as Error).message : null
          }
        />
      )}
    </div>
  );
}

// ── GSC card ──────────────────────────────────────────────────────────────────

function GSCCard({
  propertyId,
  property,
  syncStatus,
  onSaved,
  onSyncDone,
}: {
  propertyId: number;
  property: PropertyResponse;
  syncStatus: IntegrationSyncStatus | null;
  onSaved: () => void;
  onSyncDone: () => void;
}) {
  const [inputValue, setInputValue] = useState("");
  const [showLinkForm, setShowLinkForm] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  const linked = !!property.gsc_site_url;

  const linkMutation = useMutation({
    mutationFn: (siteUrl: string) => propertiesApi.linkGSC(propertyId, siteUrl),
    onSuccess: () => {
      onSaved();
      setShowLinkForm(false);
      setShowPicker(false);
      setInputValue("");
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: () => propertiesApi.unlinkGSC(propertyId),
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-lg text-sm font-black",
              linked ? "bg-blue-500/15 text-blue-400" : "bg-slate-800 text-slate-500",
            )}
          >
            S
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Search Console</h2>
            <p className="text-xs text-slate-500">Clicks, impressions, rankings</p>
          </div>
        </div>
        <StatusBadge linked={linked} />
      </div>

      {/* Connected state */}
      {linked && !showLinkForm && (
        <>
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-slate-500">Site URL</p>
              <p className="truncate font-mono text-sm text-slate-200">
                {property.gsc_site_url}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <SyncButton
              propertyId={propertyId}
              source="gsc"
              initialStatus={syncStatus}
              onDone={onSyncDone}
            />
            <div className="flex-1" />
            <button
              onClick={() => setShowPicker(true)}
              className="text-xs text-slate-600 hover:text-slate-400 transition"
            >
              Change
            </button>
            <button
              onClick={() => unlinkMutation.mutate()}
              disabled={unlinkMutation.isPending}
              className="inline-flex items-center gap-1 rounded-lg border border-red-900/40 bg-red-950/20 px-2.5 py-1.5 text-xs font-medium text-red-400 transition hover:bg-red-950/40 disabled:opacity-50"
            >
              {unlinkMutation.isPending ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <Unlink size={11} />
              )}
              Disconnect
            </button>
          </div>

          {unlinkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(unlinkMutation.error as Error).message}
            </p>
          )}
        </>
      )}

      {/* Disconnected: primary CTA is the Google picker; manual URL is a fallback */}
      {!linked && !showLinkForm && (
        <>
          <button
            onClick={() => setShowPicker(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            <GoogleIcon size={14} /> Choose a Search Console site
          </button>
          <button
            type="button"
            onClick={() => setShowLinkForm(true)}
            className="mt-2 w-full text-center text-xs text-slate-600 hover:text-slate-400 transition"
          >
            Or enter site URL manually
          </button>
          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}
        </>
      )}

      {/* Manual entry form (fallback) */}
      {(!linked && showLinkForm) && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              linkMutation.mutate(inputValue.trim());
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="sc-domain:example.com"
              autoFocus
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || linkMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {linkMutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Save size={13} />
              )}
              Link
            </button>
            <button
              type="button"
              onClick={() => {
                setShowLinkForm(false);
                setInputValue("");
              }}
              className="rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-500 hover:text-slate-300 transition"
            >
              Cancel
            </button>
          </form>

          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}

          <div className="mt-3 space-y-1 text-xs text-slate-600">
            <p>
              Use the{" "}
              <span className="font-mono text-slate-500">sc-domain:</span>{" "}
              format for domain properties:{" "}
              <span className="font-mono text-slate-500">sc-domain:example.com</span>
            </p>
            <p>
              Or full URL for URL-prefix properties:{" "}
              <span className="font-mono text-slate-500">https://example.com/</span>{" "}
              (include trailing slash).
            </p>
          </div>
        </>
      )}

      {showPicker && (
        <GooglePickerModal
          kind="gsc"
          currentValue={property.gsc_site_url ?? null}
          onClose={() => setShowPicker(false)}
          onSelect={(value) => linkMutation.mutate(value)}
          submitting={linkMutation.isPending}
          submitError={
            linkMutation.isError ? (linkMutation.error as Error).message : null
          }
        />
      )}
    </div>
  );
}

// ── Google picker modal (shared by GA4 + GSC cards) ───────────────────────────
//
// Mirrors the Clarity / Hotjar UX: searchable list of the user's accessible
// GA4 properties or GSC sites pulled directly from Google with their stored
// refresh token. No typing of IDs.

function GooglePickerModal({
  kind,
  currentValue,
  onClose,
  onSelect,
  submitting,
  submitError,
}: {
  kind: "ga4" | "gsc";
  currentValue: string | null;
  onClose: () => void;
  onSelect: (value: string) => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const [q, setQ] = useState("");

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["google-discovery"],
    queryFn: () => authApi.discoverMine(),
    staleTime: 5 * 60_000,
  });

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  const items: Array<{ value: string; primary: string; secondary?: string }> =
    !data
      ? []
      : kind === "ga4"
        ? data.ga4_properties.map((p: GA4PropertyOption) => ({
            value: p.property_id,
            primary: p.display_name,
            secondary: `${p.account_name} · ${p.property_id}`,
          }))
        : data.gsc_sites.map((s: GSCSiteOption) => ({
            value: s.site_url,
            primary: s.site_url,
            secondary: s.permission_level,
          }));

  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? items.filter(
        (it) =>
          it.primary.toLowerCase().includes(needle) ||
          (it.secondary?.toLowerCase().includes(needle) ?? false),
      )
    : items;

  const title =
    kind === "ga4" ? "Choose a GA4 property" : "Choose a Search Console site";
  const subtitle =
    kind === "ga4"
      ? "These are the GA4 properties your Google account has access to."
      : "These are the verified Search Console sites your Google account has access to.";

  // Highlight what's currently linked so the user can spot it
  const currentNorm =
    kind === "ga4" ? currentValue?.replace("properties/", "") ?? null : currentValue;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => !submitting && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white">{title}</h3>
            <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-800 hover:text-white transition disabled:opacity-50"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search */}
        <div className="px-6 pb-3">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={
                kind === "ga4" ? "Search for properties" : "Search for sites"
              }
              autoFocus
              className="w-full rounded-xl border border-slate-700 bg-slate-800 pl-9 pr-3 py-2.5 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
            />
          </div>
        </div>

        {/* List */}
        <div className="max-h-80 overflow-y-auto border-t border-slate-800/60 px-3 py-2">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-xs text-slate-500">
              <Loader2 size={14} className="animate-spin" />
              Loading from Google…
            </div>
          )}

          {isError && (
            <div className="flex flex-col items-start gap-2 px-3 py-4 text-xs">
              <p className="text-red-400">{(error as Error).message}</p>
              <button
                onClick={() => refetch()}
                className="text-brand-400 hover:text-brand-300"
              >
                Try again
              </button>
            </div>
          )}

          {data && filtered.length === 0 && !isLoading && (
            <div className="px-3 py-6 text-center text-xs text-slate-500">
              {needle ? (
                <>No matches for &ldquo;{q}&rdquo;.</>
              ) : kind === "ga4" ? (
                <>
                  No GA4 properties found for this Google account.
                  <br />
                  Confirm Viewer access in GA4 → Admin → Account access.
                </>
              ) : (
                <>
                  No verified Search Console sites for this Google account.
                  <br />
                  Verify a site at{" "}
                  <a
                    href="https://search.google.com/search-console"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-400 hover:underline"
                  >
                    search.google.com/search-console
                  </a>{" "}
                  then come back.
                </>
              )}
            </div>
          )}

          {data &&
            filtered.map((it) => {
              const isCurrent = currentNorm === it.value;
              return (
                <button
                  key={`${kind}-${it.value}`}
                  type="button"
                  onClick={() => onSelect(it.value)}
                  disabled={submitting}
                  className={clsx(
                    "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left transition disabled:opacity-50",
                    isCurrent
                      ? "bg-brand-600/15 ring-1 ring-brand-500/40"
                      : "hover:bg-slate-800/60",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-white" title={it.primary}>
                      {it.primary}
                    </p>
                    {it.secondary && (
                      <p
                        className="truncate text-[11px] text-slate-500 font-mono"
                        title={it.secondary}
                      >
                        {it.secondary}
                      </p>
                    )}
                  </div>
                  {isCurrent ? (
                    <span className="flex-shrink-0 rounded bg-brand-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-brand-300">
                      Linked
                    </span>
                  ) : (
                    <CheckCircle2 size={14} className="flex-shrink-0 text-slate-700" />
                  )}
                </button>
              );
            })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-slate-800/60 px-6 py-3">
          <div className="min-w-0 flex-1 text-xs text-slate-500">
            {submitError && <span className="text-red-400">{submitError}</span>}
            {!submitError && isFetching && !isLoading && (
              <span className="text-slate-600">Refreshing…</span>
            )}
            {!submitError && !isFetching && data && (
              <span>
                {filtered.length} {filtered.length === 1 ? "item" : "items"}
              </span>
            )}
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-50 transition"
          >
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}

// ── LLM Config card ───────────────────────────────────────────────────────────

const PROVIDER_MODELS: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-6", "claude-opus-4-5", "claude-haiku-3-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  google: ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
};

function LLMConfigCard({ propertyId }: { propertyId: number }) {
  const { data: config, isLoading } = useQuery({
    queryKey: ["llm-config", propertyId],
    queryFn: () => propertiesApi.getLLMConfig(propertyId),
    staleTime: 60_000,
  });

  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);

  // Sync form from loaded config
  useEffect(() => {
    if (config) {
      setProvider(config.llm_provider);
      setModel(config.llm_model);
    }
  }, [config]);

  function handleProviderChange(p: string) {
    setProvider(p);
    setModel((PROVIDER_MODELS[p] ?? [])[0] ?? "");
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      propertiesApi.updateLLMConfig(propertyId, {
        llm_provider: provider,
        llm_model: model,
        ...(apiKey.trim() ? { llm_api_key: apiKey.trim() } : {}),
      }),
    onSuccess: () => {
      setSaved(true);
      setApiKey("");
      setTimeout(() => setSaved(false), 3_000);
    },
  });

  const models = PROVIDER_MODELS[provider] ?? [];

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-5 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500/15">
          <KeyRound size={15} className="text-brand-400" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-white">AI Model</h2>
          <p className="text-xs text-slate-500">
            LLM used for briefs, insights, and chat
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="h-24 animate-pulse rounded-xl bg-slate-800" />
      ) : (
        <div className="space-y-4">
          {/* Provider */}
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-400">
              Provider
            </label>
            <div className="flex gap-2">
              {Object.keys(PROVIDER_MODELS).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => handleProviderChange(p)}
                  className={clsx(
                    "rounded-lg border px-3 py-1.5 text-xs font-semibold capitalize transition",
                    provider === p
                      ? "border-brand-500 bg-brand-600/20 text-brand-300"
                      : "border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300",
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Model */}
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-400">
              Model
            </label>
            <div className="relative">
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full appearance-none rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500"
              />
            </div>
          </div>

          {/* API Key override */}
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-400">
              API Key{" "}
              <span className="font-normal text-slate-600">
                (optional — leave blank to use system default)
              </span>
            </label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  config?.has_api_key_override
                    ? "••••••••  (stored — enter new to replace)"
                    : "sk-…"
                }
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 pr-16 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute inset-y-0 right-3 text-xs text-slate-600 hover:text-slate-300 transition"
              >
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {/* Save */}
          <div className="flex items-center gap-3 pt-1">
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saveMutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : saved ? (
                <Check size={13} />
              ) : (
                <Save size={13} />
              )}
              {saveMutation.isPending ? "Saving…" : saved ? "Saved!" : "Save"}
            </button>

            {saveMutation.isError && (
              <p className="text-xs text-red-400">
                {(saveMutation.error as Error).message}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Property info (read-only) ─────────────────────────────────────────────────

function PropertyInfoCard({ property }: { property: PropertyResponse }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <h2 className="mb-4 text-sm font-semibold text-slate-300">Property</h2>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="mb-1 text-xs text-slate-500">Display name</p>
          <p className="font-medium text-white">{property.display_name}</p>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500">Status</p>
          <span
            className={clsx(
              "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold",
              property.status === "active"
                ? "border-green-500/30 bg-green-950/50 text-green-400"
                : "border-amber-500/30 bg-amber-950/50 text-amber-400",
            )}
          >
            {property.status}
          </span>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500">Timezone</p>
          <p className="text-slate-300">{property.timezone}</p>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500">Currency</p>
          <p className="text-slate-300">{property.currency}</p>
        </div>
      </div>
    </div>
  );
}

// ── Shared helpers ─────────────────────────────────────────────────────────────

function StatusBadge({ linked }: { linked: boolean }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        linked
          ? "border-green-500/30 bg-green-950/40 text-green-400"
          : "border-slate-700 bg-slate-800/60 text-slate-500",
      )}
    >
      {linked ? (
        <>
          <CheckCircle2 size={10} />
          Connected
        </>
      ) : (
        <>
          <AlertCircle size={10} />
          Not connected
        </>
      )}
    </span>
  );
}

function timeAgo(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function GoogleIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48">
      <path
        fill="#FFC107"
        d="M43.6 20.2H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.7-.4-3.8z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 15.8 19 13 24 13c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4c-7.6 0-14.2 4.3-17.7 10.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.5 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8H6.3C9.7 39.5 16.4 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.2H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.3 5.6l6.2 5.2C37 37.6 44 32 44 24c0-1.3-.1-2.7-.4-3.8z"
      />
    </svg>
  );
}

// ── Conversion Events card ────────────────────────────────────────────────────

function ConversionEventsCard({
  propertyId,
  property,
  onSaved,
}: {
  propertyId: number;
  property: PropertyResponse;
  onSaved: () => void;
}) {
  const queryClient = useQueryClient();
  const ga4Linked = !!property.ga4_property_id;

  const {
    data: available,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["available-events", propertyId],
    queryFn: () => propertiesApi.getAvailableEvents(propertyId),
    enabled: ga4Linked,
    staleTime: 60_000,
  });

  const initial = property.primary_conversion_events ?? [];
  const [selected, setSelected] = useState<string[]>(initial);
  const [saved, setSaved] = useState(false);

  // Keep local state synced when the property reloads after save
  useEffect(() => {
    setSelected(property.primary_conversion_events ?? []);
  }, [property.primary_conversion_events]);

  const mutation = useMutation({
    mutationFn: (events: string[]) =>
      propertiesApi.setPrimaryConversionEvents(propertyId, events),
    onSuccess: () => {
      onSaved();
      queryClient.invalidateQueries({ queryKey: ["overview", propertyId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2_500);
    },
  });

  const toggle = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const dirty =
    selected.length !== initial.length ||
    selected.some((n, i) => n !== initial[i]);

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-4 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/15">
          <Target size={15} className="text-emerald-400" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-white">
            Primary conversion events
          </h2>
          <p className="text-xs text-slate-500">
            Pick which GA4 events count as conversions on the dashboard
          </p>
        </div>
      </div>

      {!ga4Linked && (
        <p className="text-xs text-slate-500">
          Connect Google Analytics 4 to choose conversion events.
        </p>
      )}

      {ga4Linked && isLoading && (
        <div className="h-24 animate-pulse rounded-xl bg-slate-800" />
      )}

      {ga4Linked && isError && (
        <p className="text-xs text-red-400">
          Couldn&apos;t load events: {(error as Error).message}
        </p>
      )}

      {ga4Linked && available && available.length === 0 && (
        <div className="rounded-lg border border-slate-700/50 bg-slate-800/40 p-3 text-xs text-slate-400">
          No GA4 events recorded yet for this property. Run a sync first, then
          come back here.
        </div>
      )}

      {ga4Linked && available && available.length > 0 && (
        <>
          <p className="mb-3 text-xs text-slate-500">
            Each selected event shows on the Overview page as a "Conv. rate" KPI
            (event count / total sessions). Pick the 1–3 events that matter
            most — newsletter, contact form, signup, purchase, etc.
          </p>

          <div className="max-h-80 space-y-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/40 p-2">
            {available.map((ev) => {
              const isSelected = selected.includes(ev.event_name);
              return (
                <button
                  key={ev.event_name}
                  type="button"
                  onClick={() => toggle(ev.event_name)}
                  className={clsx(
                    "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-xs transition",
                    isSelected
                      ? "bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/40"
                      : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
                  )}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      className={clsx(
                        "flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border",
                        isSelected
                          ? "border-emerald-400 bg-emerald-500/30"
                          : "border-slate-600 bg-transparent",
                      )}
                    >
                      {isSelected && <Check size={11} />}
                    </span>
                    <span className="truncate font-mono">{ev.event_name}</span>
                    {ev.is_ga4_conversion && (
                      <span className="flex-shrink-0 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-400">
                        GA4 Conv
                      </span>
                    )}
                  </span>
                  <span className="flex-shrink-0 font-mono text-[11px] text-slate-600">
                    {ev.total_count.toLocaleString()}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() => mutation.mutate(selected)}
              disabled={!dirty || mutation.isPending || selected.length > 10}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : saved ? (
                <Check size={13} />
              ) : (
                <Save size={13} />
              )}
              {mutation.isPending
                ? "Saving…"
                : saved
                  ? "Saved"
                  : `Save${dirty ? ` (${selected.length})` : ""}`}
            </button>

            <span className="text-xs text-slate-600">
              {selected.length === 0 && "No events selected — conversion-rate KPIs hidden"}
              {selected.length > 0 && selected.length <= 10 &&
                `${selected.length} event${selected.length === 1 ? "" : "s"} selected`}
              {selected.length > 10 && (
                <span className="text-amber-400">Max 10 events</span>
              )}
            </span>

            {mutation.isError && (
              <span className="text-xs text-red-400">
                {(mutation.error as Error).message}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Microsoft Clarity card ───────────────────────────────────────────────────

function ClarityCard({
  propertyId,
  property,
  onSaved,
}: {
  propertyId: number;
  property: PropertyResponse;
  onSaved: () => void;
}) {
  const initial = property.clarity_project_id ?? "";
  const [value, setValue] = useState(initial);
  const [saved, setSaved] = useState(false);

  // API token section
  const [tokenValue, setTokenValue] = useState("");
  const [tokenSaved, setTokenSaved] = useState(false);
  const hasToken = !!property.has_clarity_api_token;

  useEffect(() => {
    setValue(property.clarity_project_id ?? "");
  }, [property.clarity_project_id]);

  const linked = !!property.clarity_project_id;
  const dirty = value.trim().toLowerCase() !== initial.toLowerCase();
  const tokenDirty = tokenValue.trim().length > 0;

  const saveMutation = useMutation({
    mutationFn: () =>
      propertiesApi.setClarityProjectId(propertyId, value.trim() || null),
    onSuccess: () => {
      onSaved();
      setSaved(true);
      setTimeout(() => setSaved(false), 2_500);
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: () => propertiesApi.setClarityProjectId(propertyId, null),
    onSuccess: () => {
      onSaved();
      setValue("");
      setTokenValue("");
    },
  });

  const saveTokenMutation = useMutation({
    mutationFn: () =>
      propertiesApi.setClarityApiToken(propertyId, tokenValue.trim() || null),
    onSuccess: () => {
      onSaved();
      setTokenValue("");
      setTokenSaved(true);
      setTimeout(() => setTokenSaved(false), 2_500);
    },
  });

  const clearTokenMutation = useMutation({
    mutationFn: () => propertiesApi.setClarityApiToken(propertyId, null),
    onSuccess: () => {
      onSaved();
    },
  });

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-lg",
              linked ? "bg-purple-500/15 text-purple-300" : "bg-slate-800 text-slate-500",
            )}
          >
            <Activity size={15} />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Microsoft Clarity</h2>
            <p className="text-xs text-slate-500">
              Heatmaps, session recordings, rage clicks, frustration scores
            </p>
          </div>
        </div>
        <StatusBadge linked={linked} />
      </div>

      {linked && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-slate-500">Project ID</p>
            <p className="truncate font-mono text-sm text-slate-200">
              {property.clarity_project_id}
            </p>
          </div>
          <a
            href={`https://clarity.microsoft.com/projects/view/${property.clarity_project_id}/dashboard`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 text-brand-500 hover:text-brand-400 transition"
            title="Open in Clarity"
          >
            <ExternalLink size={14} />
          </a>
        </div>
      )}

      {/* ── Project ID row ── */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) saveMutation.mutate();
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="abcd1234ef  (or paste full Clarity URL)"
          className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 font-mono text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
        />
        <button
          type="submit"
          disabled={!dirty || saveMutation.isPending}
          className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saveMutation.isPending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : saved ? (
            <Check size={13} />
          ) : (
            <Save size={13} />
          )}
          {saved ? "Saved" : linked ? "Update" : "Link"}
        </button>
        {linked && (
          <button
            type="button"
            onClick={() => unlinkMutation.mutate()}
            disabled={unlinkMutation.isPending}
            className="inline-flex items-center gap-1 rounded-xl border border-red-900/40 bg-red-950/20 px-2.5 py-1.5 text-xs font-medium text-red-400 transition hover:bg-red-950/40 disabled:opacity-50"
            title="Unlink Clarity"
          >
            {unlinkMutation.isPending ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <Unlink size={11} />
            )}
          </button>
        )}
      </form>

      {saveMutation.isError && (
        <p className="mt-2 text-xs text-red-400">
          {(saveMutation.error as Error).message}
        </p>
      )}

      {/* ── API token row (only shown when project ID is linked) ── */}
      {linked && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound size={13} className="text-slate-500" />
              <span className="text-xs font-medium text-slate-400">
                Data Export API token
              </span>
              {hasToken && (
                <span className="rounded-full bg-emerald-900/40 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                  Configured
                </span>
              )}
            </div>
            {hasToken && (
              <button
                type="button"
                onClick={() => clearTokenMutation.mutate()}
                disabled={clearTokenMutation.isPending}
                className="text-xs text-red-500 hover:text-red-400 transition disabled:opacity-50"
              >
                {clearTokenMutation.isPending ? "Removing..." : "Remove token"}
              </button>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (tokenDirty) saveTokenMutation.mutate();
            }}
            className="flex gap-2"
          >
            <input
              type="password"
              value={tokenValue}
              onChange={(e) => setTokenValue(e.target.value)}
              placeholder={
                hasToken
                  ? "Enter new token to replace..."
                  : "Paste your Clarity Data Export API token..."
              }
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 font-mono text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
            />
            <button
              type="submit"
              disabled={!tokenDirty || saveTokenMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saveTokenMutation.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : tokenSaved ? (
                <Check size={13} />
              ) : (
                <Save size={13} />
              )}
              {tokenSaved ? "Saved" : hasToken ? "Replace" : "Save token"}
            </button>
          </form>

          {saveTokenMutation.isError && (
            <p className="text-xs text-red-400">
              {(saveTokenMutation.error as Error).message}
            </p>
          )}

          <p className="text-xs text-slate-600">
            Get a Data Export API token from{" "}
            <a
              href="https://clarity.microsoft.com/account"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-500 hover:text-brand-400"
            >
              Clarity Account Settings
            </a>
            . Once added, PRISM pulls per-page frustration metrics nightly and
            surfaces them in the Pages report.
          </p>
        </div>
      )}

      <p className="mt-3 text-xs text-slate-600">
        Install the Clarity tracking snippet on your site at{" "}
        <a
          href="https://clarity.microsoft.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand-500 hover:text-brand-400"
        >
          clarity.microsoft.com
        </a>
        , then paste your project ID here. PRISM uses it to deep-link heatmaps
        and session recordings from the Pages report.
      </p>
    </div>
  );
}

// ── CWV + Actions settings ────────────────────────────────────────────────────

function CWVSettingsCard({ propertyId }: { propertyId: number }) {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["cwv-settings", propertyId],
    queryFn: () => propertySettingsApi.get(propertyId),
    staleTime: 60_000,
  });

  const [psiKey, setPsiKey] = useState("");
  const [psiKeySaved, setPsiKeySaved] = useState(false);
  const [showPsiKey, setShowPsiKey] = useState(false);

  const mutation = useMutation({
    mutationFn: (body: PropertySettingsUpdate) =>
      propertySettingsApi.update(propertyId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cwv-settings", propertyId] }),
  });

  const psiKeyMutation = useMutation({
    mutationFn: (key: string) =>
      propertySettingsApi.update(propertyId, { psi_api_key: key }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cwv-settings", propertyId] });
      setPsiKey("");
      setPsiKeySaved(true);
      setTimeout(() => setPsiKeySaved(false), 2_500);
    },
  });

  function toggle(field: keyof Omit<PropertySettingsResponse, "property_id" | "has_psi_api_key">) {
    if (!data) return;
    mutation.mutate({ [field]: !data[field] });
  }

  function setCount(n: number) {
    mutation.mutate({ cwv_top_pages_count: n });
  }

  const settings = data;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-5 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500/15 text-brand-300">
          <Gauge size={15} />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-white">Performance & actions</h2>
          <p className="text-xs text-slate-500">
            Core Web Vitals audit schedule and action safety gates
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={14} className="animate-spin" />
          Loading settings...
        </div>
      )}

      {settings && (
        <div className="space-y-4">
          {/* CWV audit toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-white">CWV nightly audit</p>
              <p className="text-xs text-slate-500">
                Run PageSpeed Insights on top pages every night at 03:00 UTC
              </p>
            </div>
            <button
              onClick={() => toggle("cwv_audit_enabled")}
              disabled={mutation.isPending}
              className={clsx(
                "relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                settings.cwv_audit_enabled ? "bg-brand-600" : "bg-slate-700",
              )}
            >
              <span
                className={clsx(
                  "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                  settings.cwv_audit_enabled ? "translate-x-5" : "translate-x-0",
                )}
              />
            </button>
          </div>

          {/* Mobile / desktop strategy */}
          <div className="flex items-center gap-6 rounded-xl border border-slate-700/50 bg-slate-800/40 px-4 py-3">
            <p className="flex-1 text-xs text-slate-400">Audit strategies</p>
            {[
              { label: "Mobile", field: "cwv_mobile_enabled" as const },
              { label: "Desktop", field: "cwv_desktop_enabled" as const },
            ].map(({ label, field }) => (
              <label key={field} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!settings[field]}
                  onChange={() => toggle(field)}
                  disabled={mutation.isPending}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-700 accent-brand-500"
                />
                <span className="text-xs text-slate-300">{label}</span>
              </label>
            ))}
          </div>

          {/* Top pages count */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-white">Pages per audit run</p>
              <p className="text-xs text-slate-500">
                Top N pages by sessions to audit each night (1–100)
              </p>
            </div>
            <input
              type="number"
              min={1}
              max={100}
              value={settings.cwv_top_pages_count}
              onChange={(e) => {
                const n = parseInt(e.target.value, 10);
                if (!isNaN(n) && n >= 1 && n <= 100) setCount(n);
              }}
              className="w-20 rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-center text-sm text-white outline-none focus:border-brand-500"
            />
          </div>

          {/* PSI API key */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound size={13} className="text-slate-500" />
                <span className="text-xs font-medium text-slate-400">
                  PageSpeed Insights API key
                </span>
                {settings.has_psi_api_key && (
                  <span className="rounded-full bg-emerald-900/40 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                    Configured
                  </span>
                )}
              </div>
              {settings.has_psi_api_key && (
                <button
                  type="button"
                  onClick={() => psiKeyMutation.mutate("")}
                  disabled={psiKeyMutation.isPending}
                  className="text-xs text-red-500 hover:text-red-400 transition disabled:opacity-50"
                >
                  {psiKeyMutation.isPending ? "Removing…" : "Remove key"}
                </button>
              )}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (psiKey.trim()) psiKeyMutation.mutate(psiKey.trim());
              }}
              className="flex gap-2"
            >
              <div className="relative flex-1">
                <input
                  type={showPsiKey ? "text" : "password"}
                  value={psiKey}
                  onChange={(e) => setPsiKey(e.target.value)}
                  placeholder={
                    settings.has_psi_api_key
                      ? "Enter new key to replace…"
                      : "AIzaSy…"
                  }
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 pr-14 font-mono text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
                />
                <button
                  type="button"
                  onClick={() => setShowPsiKey((v) => !v)}
                  className="absolute inset-y-0 right-3 text-xs text-slate-600 hover:text-slate-300 transition"
                >
                  {showPsiKey ? "Hide" : "Show"}
                </button>
              </div>
              <button
                type="submit"
                disabled={!psiKey.trim() || psiKeyMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {psiKeyMutation.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : psiKeySaved ? (
                  <Check size={13} />
                ) : (
                  <Save size={13} />
                )}
                {psiKeySaved ? "Saved" : settings.has_psi_api_key ? "Replace" : "Save key"}
              </button>
            </form>
            {psiKeyMutation.isError && (
              <p className="text-xs text-red-400">
                {(psiKeyMutation.error as Error).message}
              </p>
            )}
            <p className="text-xs text-slate-600">
              Get a free API key from{" "}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-500 hover:text-brand-400"
              >
                Google Cloud Console
              </a>{" "}
              — enable the PageSpeed Insights API, create an API key, restrict it
              to that API. Without a key, PSI audits still work but at a lower
              quota.
            </p>
          </div>

          <div className="border-t border-slate-800 pt-4">
            {/* Destructive actions gate */}
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-1.5">
                  <AlertTriangle size={13} className="text-amber-400" />
                  <p className="text-sm font-medium text-white">Allow destructive actions</p>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Permit the AI analyst to queue sitemap deletion. When off, delete
                  requests are blocked at execution time regardless of confirmation.
                </p>
              </div>
              <button
                onClick={() => toggle("allow_destructive_actions")}
                disabled={mutation.isPending}
                className={clsx(
                  "relative mt-0.5 inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                  settings.allow_destructive_actions ? "bg-amber-600" : "bg-slate-700",
                )}
              >
                <span
                  className={clsx(
                    "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                    settings.allow_destructive_actions ? "translate-x-5" : "translate-x-0",
                  )}
                />
              </button>
            </div>
          </div>

          {mutation.isError && (
            <p className="text-xs text-red-400">
              {(mutation.error as Error).message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SettingsSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-32 rounded-2xl bg-slate-900" />
      <div className="h-48 rounded-2xl bg-slate-900" />
      <div className="h-48 rounded-2xl bg-slate-900" />
      <div className="h-56 rounded-2xl bg-slate-900" />
      <div className="h-56 rounded-2xl bg-slate-900" />
      <div className="h-48 rounded-2xl bg-slate-900" />
    </div>
  );
}
