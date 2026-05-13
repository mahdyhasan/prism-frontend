"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  FileText,
  Flame,
  PlayCircle,
  RefreshCw,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  DateRangePicker,
  type DatePreset,
  type CompareTo,
} from "@/components/dashboard/date-range-picker";
import { useProperty } from "@/hooks/use-properties";
import {
  clarityHeatmapUrl,
  clarityRecordingsUrl,
  isClarityLinked,
  isGA4Linked,
} from "@/lib/property-features";
import {
  formatCurrency,
  formatDuration,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import {
  pagesApi,
  type DeviceCategory,
  type PageRow,
  type PageSortKey,
} from "@/lib/api-client";

const PRESET_DAYS: Record<DatePreset, number> = {
  last_7d: 7,
  last_30d: 30,
  last_90d: 90,
  last_12m: 365,
  last_14m: 425,
};

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function rangeFor(preset: DatePreset): { start: string; end: string } {
  const days = PRESET_DAYS[preset];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { start: toISO(start), end: toISO(end) };
}

type SortPreset =
  | "most_traffic"
  | "best_converters"
  | "worst_bounce"
  | "worst_exit"
  | "hidden_gems"
  | "lowest_health";

const SORT_PRESETS: Record<
  SortPreset,
  { label: string; sort_by: PageSortKey; sort_desc: boolean; min_sessions: number; tip: string }
> = {
  most_traffic: {
    label: "Most traffic",
    sort_by: "sessions",
    sort_desc: true,
    min_sessions: 1,
    tip: "Highest-session pages first",
  },
  best_converters: {
    label: "Best converters",
    sort_by: "conv_rate",
    sort_desc: true,
    min_sessions: 50,
    tip: "Highest conversion rate, sessions floor 50",
  },
  worst_bounce: {
    label: "Worst bounce",
    sort_by: "bounce_rate",
    sort_desc: true,
    min_sessions: 50,
    tip: "Highest bounce rate, sessions floor 50",
  },
  worst_exit: {
    label: "Worst exit",
    sort_by: "exit_rate",
    sort_desc: true,
    min_sessions: 50,
    tip: "Pages users leave from most often — exit rate descending, sessions floor 50",
  },
  hidden_gems: {
    label: "Hidden gems",
    sort_by: "impressions",
    sort_desc: true,
    min_sessions: 1,
    tip: "High GSC impressions — usually means rank potential",
  },
  lowest_health: {
    label: "Lowest health",
    sort_by: "health_score",
    sort_desc: false,
    min_sessions: 50,
    tip: "Worst composite health score, sessions floor 50",
  },
};

export default function PagesPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);

  const [preset, setPreset] = useState<DatePreset>("last_30d");
  const [compareTo, setCompareTo] = useState<CompareTo>("none");
  const [sortPreset, setSortPreset] = useState<SortPreset>("most_traffic");
  const [sortBy, setSortBy] = useState<PageSortKey>("sessions");
  const [sortDesc, setSortDesc] = useState(true);
  const [minSessions, setMinSessions] = useState(1);
  const [device, setDevice] = useState<DeviceCategory | null>(null);

  const { data: property } = useProperty(propertyId);
  const ga4Linked = property ? isGA4Linked(property) : true;
  const clarityProjectId =
    property && isClarityLinked(property) ? property.clarity_project_id! : null;

  // The compareTo control is shared with /overview but we don't actually use it
  // here. Suppress unused-state warnings.
  void compareTo;
  void setCompareTo;

  // Apply preset to sort + min_sessions when the user picks a preset chip
  function applyPreset(p: SortPreset) {
    setSortPreset(p);
    const cfg = SORT_PRESETS[p];
    setSortBy(cfg.sort_by);
    setSortDesc(cfg.sort_desc);
    setMinSessions(cfg.min_sessions);
  }

  // Clicking a column header overrides the preset's sort key (kept for power-user UX)
  function clickColumnSort(key: PageSortKey) {
    if (sortBy === key) {
      setSortDesc((v) => !v);
    } else {
      setSortBy(key);
      setSortDesc(true);
    }
  }

  const { start, end } = useMemo(() => rangeFor(preset), [preset]);

  const queryKey = ["pages", propertyId, start, end, minSessions, sortBy, sortDesc, device];

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey,
    queryFn: () =>
      pagesApi.list(propertyId, {
        start,
        end,
        min_sessions: minSessions,
        sort_by: sortBy,
        sort_desc: sortDesc,
        limit: 100,
        device: device ?? undefined,
      }),
    enabled: !!propertyId && ga4Linked,
    staleTime: 60_000,
  });

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Pages" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              {data && (
                <>
                  Showing {data.rows.length} of {data.total_rows} pages · {data.start_date} → {data.end_date}
                </>
              )}
            </div>
            <DateRangePicker
              preset={preset}
              compareTo="none"
              onPresetChange={setPreset}
              onCompareChange={() => {}}
            />
          </div>

          {!ga4Linked && (
            <EmptyCard
              title="GA4 not linked"
              body="Pages report needs Google Analytics 4. Link it on the Settings page."
            />
          )}

          {ga4Linked && (
            <>
              {/* Device filter chips */}
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-widest text-slate-600 mr-1">
                  Device
                </span>
                {([null, "mobile", "desktop", "tablet"] as const).map((d) => {
                  const active = device === d;
                  const label = d === null ? "All" : d[0].toUpperCase() + d.slice(1);
                  return (
                    <button
                      key={String(d)}
                      type="button"
                      onClick={() => setDevice(d)}
                      title={
                        d === null
                          ? "All devices (uses GA4 + GSC join)"
                          : `Only ${d} traffic — GSC columns hidden (no device dim in GSC)`
                      }
                      className={clsx(
                        "rounded-full border px-3 py-1 text-xs font-semibold transition",
                        active
                          ? "border-amber-500/60 bg-amber-500/10 text-amber-300"
                          : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-white",
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
                {device !== null && (
                  <span className="text-xs text-slate-600">
                    (GSC data hidden when device filter is on)
                  </span>
                )}
              </div>

              {/* Sort preset chips */}
              <div className="mb-3 flex flex-wrap items-center gap-2">
                {(Object.keys(SORT_PRESETS) as SortPreset[]).map((p) => {
                  const cfg = SORT_PRESETS[p];
                  const active = sortPreset === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => applyPreset(p)}
                      title={cfg.tip}
                      className={clsx(
                        "rounded-full border px-3 py-1 text-xs font-semibold transition",
                        active
                          ? "border-brand-500 bg-brand-600/20 text-brand-300"
                          : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-white",
                      )}
                    >
                      {cfg.label}
                    </button>
                  );
                })}
                <div className="flex-1" />
                <MinSessionsControl
                  value={minSessions}
                  onChange={setMinSessions}
                />
              </div>

              {isError && (
                <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
                  <AlertCircle size={14} />
                  <span className="flex-1">{(error as Error).message}</span>
                  <button
                    onClick={() => refetch()}
                    className="text-xs text-red-300 hover:text-red-200"
                  >
                    Retry
                  </button>
                </div>
              )}

              {isLoading && <TableSkeleton />}

              {data && data.rows.length === 0 && !isLoading && (
                <EmptyCard
                  title="No page data for this period"
                  body="Either no pages cleared the sessions floor, or the cross-source materialization hasn't run yet. Try lowering the floor, widening the date range, or running a sync from Settings."
                  action={
                    <button
                      onClick={() => refetch()}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:border-slate-600 hover:text-white"
                    >
                      <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
                      Refresh
                    </button>
                  }
                />
              )}

              {data && data.rows.length > 0 && (
                <PagesTable
                  rows={data.rows}
                  sortBy={sortBy}
                  sortDesc={sortDesc}
                  onSort={clickColumnSort}
                  currency="USD"
                  clarityProjectId={clarityProjectId}
                />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// ── Table ──────────────────────────────────────────────────────────────────

function PagesTable({
  rows,
  sortBy,
  sortDesc,
  onSort,
  currency,
  clarityProjectId,
}: {
  rows: PageRow[];
  sortBy: PageSortKey;
  sortDesc: boolean;
  onSort: (key: PageSortKey) => void;
  currency: string;
  clarityProjectId: string | null;
}) {
  const showRevenue = rows.some((r) => r.revenue > 0);
  const showGSC = rows.some((r) => r.impressions > 0 || r.clicks > 0);
  const showClarity = !!clarityProjectId;

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900/60">
            <Th>Page</Th>
            <Th align="right" sortKey="sessions" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Sessions
            </Th>
            <Th align="right" sortKey="conv_rate" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Conv. rate
            </Th>
            <Th align="right" sortKey="engagement_rate" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Engaged
            </Th>
            <Th align="right" sortKey="bounce_rate" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Bounce
            </Th>
            <Th align="right" sortKey="exit_rate" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Exit rate
            </Th>
            <Th align="right" sortKey="avg_duration" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Avg duration
            </Th>
            {showRevenue && <Th align="right">Revenue</Th>}
            {showGSC && (
              <>
                <Th align="right" sortKey="clicks" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
                  Clicks
                </Th>
                <Th align="right" sortKey="impressions" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
                  Impressions
                </Th>
                <Th align="right" sortKey="position" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
                  Position
                </Th>
              </>
            )}
            <Th align="right" sortKey="health_score" sortBy={sortBy} sortDesc={sortDesc} onSort={onSort}>
              Health
            </Th>
            {showClarity && <Th align="right">Clarity</Th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {rows.map((row) => (
            <tr key={row.page} className="hover:bg-slate-800/30">
              <td className="px-3 py-2.5 text-left">
                <span
                  className="block max-w-[280px] truncate text-slate-200"
                  title={row.page}
                >
                  {row.page}
                </span>
              </td>
              <Td>{formatNumber(row.sessions)}</Td>
              <Td>{row.conversion_rate == null ? <Dash /> : formatPercent(row.conversion_rate)}</Td>
              <Td>{row.engagement_rate == null ? <Dash /> : formatPercent(row.engagement_rate)}</Td>
              <Td>{formatPercent(row.bounce_rate)}</Td>
              <Td>{row.exit_rate == null ? <Dash /> : formatPercent(row.exit_rate)}</Td>
              <Td>{formatDuration(row.avg_session_duration)}</Td>
              {showRevenue && (
                <Td>{row.revenue > 0 ? formatCurrency(row.revenue, currency) : <Dash />}</Td>
              )}
              {showGSC && (
                <>
                  <Td>{row.clicks > 0 ? formatNumber(row.clicks) : <Dash />}</Td>
                  <Td>{row.impressions > 0 ? formatNumber(row.impressions) : <Dash />}</Td>
                  <Td>{row.avg_position > 0 ? row.avg_position.toFixed(1) : <Dash />}</Td>
                </>
              )}
              <td className="px-3 py-2.5 text-right">
                <HealthBadge score={row.health_score} />
              </td>
              {showClarity && (
                <td className="px-3 py-2.5 text-right">
                  <div className="inline-flex items-center gap-1">
                    <a
                      href={clarityHeatmapUrl(clarityProjectId!, row.page)}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`View heatmap for ${row.page}`}
                      className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-700 text-slate-400 transition hover:border-orange-500/60 hover:bg-orange-500/10 hover:text-orange-400"
                    >
                      <Flame size={11} />
                    </a>
                    <a
                      href={clarityRecordingsUrl(clarityProjectId!, row.page)}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`Session recordings for ${row.page}`}
                      className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-700 text-slate-400 transition hover:border-purple-500/60 hover:bg-purple-500/10 hover:text-purple-400"
                    >
                      <PlayCircle size={11} />
                    </a>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "left",
  sortKey,
  sortBy,
  sortDesc,
  onSort,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  sortKey?: PageSortKey;
  sortBy?: PageSortKey;
  sortDesc?: boolean;
  onSort?: (k: PageSortKey) => void;
}) {
  const sortable = !!sortKey && !!onSort;
  const isActive = sortable && sortBy === sortKey;
  return (
    <th
      className={clsx(
        "select-none px-3 py-2.5 text-xs font-semibold uppercase tracking-widest text-slate-500",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {sortable ? (
        <button
          type="button"
          onClick={() => onSort!(sortKey!)}
          className={clsx(
            "inline-flex items-center gap-1 transition",
            isActive ? "text-slate-200" : "hover:text-slate-300",
          )}
        >
          {children}
          {isActive && (sortDesc ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
        </button>
      ) : (
        children
      )}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">{children}</td>
  );
}

function Dash() {
  return <span className="text-slate-700">—</span>;
}

function HealthBadge({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <span
        className="text-slate-700"
        title="Not enough sessions to compute a stable health score"
      >
        —
      </span>
    );
  }
  const pct = Math.round(score * 100);
  const color =
    score >= 0.65
      ? "border-green-700/50 bg-green-950/40 text-green-400"
      : score < 0.30
        ? "border-red-700/50 bg-red-950/40 text-red-400"
        : "border-slate-700 bg-slate-800/60 text-slate-300";
  return (
    <span
      title="Composite of conversion rate (40%), engagement rate (30%), and inverse bounce rate (30%)"
      className={clsx(
        "inline-flex w-12 items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums",
        color,
      )}
    >
      {pct}
    </span>
  );
}

// ── Filters ────────────────────────────────────────────────────────────────

function MinSessionsControl({
  value,
  onChange,
}: {
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="inline-flex items-center gap-2 rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-500">
      Min sessions
      <input
        type="number"
        min={0}
        step={10}
        value={value}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        className="w-16 bg-transparent text-right tabular-nums text-slate-200 outline-none"
      />
    </label>
  );
}

// ── Empty / loading states ─────────────────────────────────────────────────

function EmptyCard({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-slate-500">
        <FileText size={18} />
      </div>
      <h3 className="mb-1 text-sm font-semibold text-white">{title}</h3>
      <p className="mx-auto max-w-md text-xs text-slate-500">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-8 rounded bg-slate-800/60" />
        ))}
      </div>
    </div>
  );
}
