"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { signIn } from "next-auth/react";
import { clsx } from "clsx";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  Unlink,
  WifiOff,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  authApi,
  propertiesApi,
  syncApi,
  type IntegrationSyncStatus,
  type PropertyResponse,
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

  const linked = !!property.ga4_property_id;
  const displayId = property.ga4_property_id?.replace("properties/", "") ?? "";

  const linkMutation = useMutation({
    mutationFn: (ga4Id: string) => propertiesApi.linkGA4(propertyId, ga4Id),
    onSuccess: () => {
      onSaved();
      setShowLinkForm(false);
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
              onClick={() => setShowLinkForm(true)}
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

      {/* Link / re-link form */}
      {(!linked || showLinkForm) && (
        <>
          {showLinkForm && (
            <p className="mb-3 text-xs text-slate-500">
              Enter a new Property ID to replace the current one.
            </p>
          )}

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
              autoFocus={showLinkForm}
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
              {linked ? "Update" : "Link"}
            </button>
            {showLinkForm && (
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
            )}
          </form>

          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}
          {linkMutation.isSuccess && !showLinkForm && (
            <p className="mt-2 text-xs text-green-400">GA4 linked. Run a sync to pull data.</p>
          )}

          {!showLinkForm && (
            <p className="mt-3 text-xs text-slate-600">
              Find your numeric Property ID in GA4 → Admin → Property Settings.
              Enter digits only (e.g.{" "}
              <span className="font-mono text-slate-500">123456789</span>).
            </p>
          )}
        </>
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

  const linked = !!property.gsc_site_url;

  const linkMutation = useMutation({
    mutationFn: (siteUrl: string) => propertiesApi.linkGSC(propertyId, siteUrl),
    onSuccess: () => {
      onSaved();
      setShowLinkForm(false);
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
              onClick={() => setShowLinkForm(true)}
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

      {/* Link / re-link form */}
      {(!linked || showLinkForm) && (
        <>
          {showLinkForm && (
            <p className="mb-3 text-xs text-slate-500">
              Enter a new site URL to replace the current one.
            </p>
          )}

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
              autoFocus={showLinkForm}
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
              {linked ? "Update" : "Link"}
            </button>
            {showLinkForm && (
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
            )}
          </form>

          {linkMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(linkMutation.error as Error).message}
            </p>
          )}
          {linkMutation.isSuccess && !showLinkForm && (
            <p className="mt-2 text-xs text-green-400">GSC linked. Run a sync to pull data.</p>
          )}

          {!showLinkForm && (
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
          )}
        </>
      )}
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

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SettingsSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-32 rounded-2xl bg-slate-900" />
      <div className="h-48 rounded-2xl bg-slate-900" />
      <div className="h-48 rounded-2xl bg-slate-900" />
      <div className="h-56 rounded-2xl bg-slate-900" />
    </div>
  );
}
