"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ExternalLink,
  TrendingUp,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  DateRangePicker,
  type DatePreset,
  type CompareTo,
} from "@/components/dashboard/date-range-picker";
import {
  searchApi,
  searchWidgetsApi,
  type SearchOpportunity,
  type SearchOverviewResponse,
  type SearchPage,
  type SearchQuery,
  type SearchType,
  type SearchTypeBreakdownItem,
} from "@/lib/api-client";
import { useProperty } from "@/hooks/use-properties";
import { isGSCLinked } from "@/lib/property-features";
import { AppearanceBreakdown } from "@/components/dashboard/appearance-breakdown";
import {
  SearchTypeTabs,
  type SearchTypeTab,
} from "@/components/dashboard/search-type-tabs";

type Tab = "queries" | "pages" | "opportunities";

interface DateRange {
  start: string;
  end: string;
  compare_start?: string;
  compare_end?: string;
}

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

function rangeFor(preset: DatePreset, compareTo: CompareTo): DateRange {
  const days = PRESET_DAYS[preset];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));

  let compare_start: string | undefined;
  let compare_end: string | undefined;

  if (compareTo === "previous_period") {
    const cEnd = new Date(start);
    cEnd.setUTCDate(cEnd.getUTCDate() - 1);
    const cStart = new Date(cEnd);
    cStart.setUTCDate(cStart.getUTCDate() - (days - 1));
    compare_start = toISO(cStart);
    compare_end = toISO(cEnd);
  } else if (compareTo === "same_period_last_year") {
    const cStart = new Date(start);
    cStart.setUTCFullYear(cStart.getUTCFullYear() - 1);
    const cEnd = new Date(end);
    cEnd.setUTCFullYear(cEnd.getUTCFullYear() - 1);
    compare_start = toISO(cStart);
    compare_end = toISO(cEnd);
  }

  return {
    start: toISO(start),
    end: toISO(end),
    compare_start,
    compare_end,
  };
}

function fmtNumber(value: number): string {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function fmtCTR(value: number): string {
  // The API may return a string (JSON serialisation quirk) or a float (ratio vs percent).
  const n = Number(value);
  if (!isFinite(n)) return "—";
  // Heuristic: values ≤ 1 are ratios (0.0432), values > 1 are already percent (4.32).
  const pct = n <= 1 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

function fmtPosition(value: number): string {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  return n.toFixed(1);
}

function truncateUrl(url: string, max = 60): string {
  if (url.length <= max) return url;
  return `${url.slice(0, max - 1)}…`;
}

export default function SearchPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const [preset, setPreset] = useState<DatePreset>("last_30d");
  const [compareTo, setCompareTo] = useState<CompareTo>("previous_period");
  const [tab, setTab] = useState<Tab>("queries");
  const [searchTypeTab, setSearchTypeTab] = useState<SearchTypeTab>("web");

  const range = useMemo(() => rangeFor(preset, compareTo), [preset, compareTo]);

  const { data: property } = useProperty(propertyId);
  const gscLinked = property ? isGSCLinked(property) : true;

  const overviewQuery = useQuery({
    queryKey: ["search-overview", propertyId, range],
    queryFn: () =>
      searchApi.getOverview(propertyId, {
        start: range.start,
        end: range.end,
        compare_start: range.compare_start,
        compare_end: range.compare_end,
      }),
    enabled: !!propertyId && gscLinked,
    staleTime: 1000 * 60 * 5,
  });

  const searchTypesQuery = useQuery({
    queryKey: ["search-types", propertyId, range.start, range.end],
    queryFn: () =>
      searchWidgetsApi.getSearchTypes(propertyId, {
        start: range.start,
        end: range.end,
      }),
    enabled: !!propertyId && gscLinked,
    staleTime: 1000 * 60 * 5,
  });

  const searchTypesData = searchTypesQuery.data ?? null;
  const searchTypeAvailability = useMemo<Partial<Record<SearchType, boolean>>>(() => {
    if (!searchTypesData) return {};
    const map: Partial<Record<SearchType, boolean>> = {};
    for (const row of searchTypesData) {
      map[row.search_type] = row.impressions > 0 || row.clicks > 0;
    }
    return map;
  }, [searchTypesData]);

  const activeSearchTypeRow: SearchTypeBreakdownItem | null = useMemo(() => {
    if (!searchTypesData) return null;
    return (
      searchTypesData.find((r) => r.search_type === searchTypeTab) ?? null
    );
  }, [searchTypesData, searchTypeTab]);

  const hasAnySearchTypeData =
    !!searchTypesData &&
    searchTypesData.some((r) => r.impressions > 0 || r.clicks > 0);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Search" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-500">
                {range.start} — {range.end}
              </p>
            </div>
            <DateRangePicker
              preset={preset}
              compareTo={compareTo}
              onPresetChange={setPreset}
              onCompareChange={setCompareTo}
            />
          </div>

          {property && !gscLinked ? (
            <GSCNotLinkedCTA />
          ) : (
            <>
              {hasAnySearchTypeData && searchTypesData && (
                <SearchTypeKPIRow row={activeSearchTypeRow} tab={searchTypeTab} />
              )}

              {overviewQuery.isLoading && <OverviewSkeleton />}
              {overviewQuery.isError && (
                <ErrorBanner
                  message={
                    (overviewQuery.error as Error | undefined)?.message ?? "Unknown error"
                  }
                />
              )}

              {overviewQuery.data && (
                <OverviewSection
                  data={overviewQuery.data}
                  propertyId={propertyId}
                />
              )}

              <div className="mt-6">
                <AppearanceBreakdown
                  propertyId={propertyId}
                  start={range.start}
                  end={range.end}
                />
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                  Search type
                </span>
                <SearchTypeTabs
                  value={searchTypeTab}
                  onChange={setSearchTypeTab}
                  available={searchTypeAvailability}
                />
              </div>

              <div className="mt-4">
                <TabBar tab={tab} onChange={setTab} />
                <div className="mt-4">
                  {searchTypeTab !== "web" && (
                    <div className="mb-3 rounded-lg border border-amber-900/60 bg-amber-950/30 px-4 py-2 text-xs text-amber-300">
                      Showing data across all search types — per-type filtering
                      coming soon.
                    </div>
                  )}
                  {tab === "queries" && (
                    <QueriesTab propertyId={propertyId} range={range} />
                  )}
                  {tab === "pages" && (
                    <PagesTab propertyId={propertyId} range={range} />
                  )}
                  {tab === "opportunities" && (
                    <OpportunitiesTab propertyId={propertyId} range={range} />
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// ─── KPIs + Trend ─────────────────────────────────────────────────────────────

function OverviewSection({
  data,
  propertyId,
}: {
  data: SearchOverviewResponse;
  propertyId: number;
}) {
  const { kpis, daily_trend } = data;
  const trend = daily_trend ?? [];
  const hasData = trend.length > 0;

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SearchKPICard
          label="Total clicks"
          value={fmtNumber(kpis.clicks)}
          delta={kpis.clicks_delta}
        />
        <SearchKPICard
          label="Total impressions"
          value={fmtNumber(kpis.impressions)}
          delta={kpis.impressions_delta}
        />
        <SearchKPICard
          label="Average CTR"
          value={fmtCTR(kpis.ctr)}
          delta={kpis.ctr_delta}
        />
        <SearchKPICard
          label="Average position"
          value={fmtPosition(kpis.avg_position)}
          delta={kpis.position_delta}
          inverted
        />
      </div>

      <div className="mb-2">
        {hasData ? (
          <SearchTrendChart data={trend} />
        ) : (
          <EmptyTrendState propertyId={propertyId} />
        )}
      </div>
    </>
  );
}

interface SearchKPICardProps {
  label: string;
  value: string;
  delta: number | null;
  /** When true (e.g. position), a positive delta is bad and shown red. */
  inverted?: boolean;
}

function SearchKPICard({ label, value, delta, inverted = false }: SearchKPICardProps) {
  const positive = delta !== null && delta > 0;
  const negative = delta !== null && delta < 0;
  const good = inverted ? negative : positive;
  const bad = inverted ? positive : negative;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </p>
      <p className="mb-2 text-3xl font-bold text-white">{value}</p>
      {delta !== null && delta !== undefined && isFinite(delta) && (
        <p
          className={clsx(
            "text-xs font-medium",
            good && "text-green-400",
            bad && "text-red-400",
            !good && !bad && "text-slate-500",
          )}
        >
          {positive ? "▲" : negative ? "▼" : "—"} {Math.abs(delta).toFixed(1)}% vs previous
        </p>
      )}
    </div>
  );
}

function SearchTrendChart({ data }: { data: SearchOverviewResponse["daily_trend"] }) {
  const formatted = data.map((d) => ({
    date: d.date.slice(5),
    clicks: d.clicks,
    impressions: d.impressions,
  }));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">
        Clicks &amp; impressions
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={formatted} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="clicksGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="imprGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="left"
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) =>
              v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)
            }
            width={40}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) =>
              v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)
            }
            width={45}
          />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 8,
            }}
            labelStyle={{ color: "#94a3b8", fontSize: 12 }}
            itemStyle={{ color: "#e2e8f0", fontSize: 12 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "#94a3b8" }}
            iconType="circle"
          />
          <Area
            yAxisId="left"
            type="monotone"
            dataKey="clicks"
            name="Clicks"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#clicksGrad)"
            dot={false}
          />
          <Area
            yAxisId="right"
            type="monotone"
            dataKey="impressions"
            name="Impressions"
            stroke="#22d3ee"
            strokeWidth={2}
            fill="url(#imprGrad)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function EmptyTrendState({ propertyId }: { propertyId: number }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900 px-6 py-12 text-center">
      <p className="mb-2 text-sm font-medium text-slate-300">No search data for this period</p>
      <p className="mb-4 text-xs text-slate-500">
        Run a GSC sync from Settings to pull in data, or choose a wider date range.
      </p>
      <Link
        href={`/properties/${propertyId}/settings` as Route}
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 transition hover:border-slate-600 hover:text-white"
      >
        Open settings
        <ExternalLink size={12} />
      </Link>
    </div>
  );
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

function TabBar({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  const tabs: { value: Tab; label: string }[] = [
    { value: "queries", label: "Queries" },
    { value: "pages", label: "Pages" },
    { value: "opportunities", label: "Opportunities" },
  ];
  return (
    <div className="inline-flex items-center rounded-lg border border-slate-700 bg-slate-900 p-0.5">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            "rounded-md px-4 py-1.5 text-xs font-medium transition",
            tab === t.value
              ? "bg-brand-600 text-white"
              : "text-slate-400 hover:text-white",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ─── Sortable table ──────────────────────────────────────────────────────────

interface ColumnDef<T> {
  key: keyof T & string;
  label: string;
  numeric?: boolean;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

interface SortableTableProps<T> {
  rows: T[];
  columns: ColumnDef<T>[];
  defaultSort: keyof T & string;
  defaultDir?: "asc" | "desc";
}

function SortableTable<T>({
  rows,
  columns,
  defaultSort,
  defaultDir = "desc",
}: SortableTableProps<T>) {
  const [sortKey, setSortKey] = useState<keyof T & string>(defaultSort);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(defaultDir);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const as = String(av ?? "");
      const bs = String(bv ?? "");
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function toggleSort(key: keyof T & string) {
    if (key === sortKey) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800">
            {columns.map((col) => {
              const active = sortKey === col.key;
              return (
                <th
                  key={col.key}
                  className={clsx(
                    "px-5 py-3 text-xs font-semibold uppercase tracking-widest text-slate-500",
                    col.numeric ? "text-right" : "text-left",
                  )}
                >
                  <button
                    onClick={() => toggleSort(col.key)}
                    className={clsx(
                      "inline-flex items-center gap-1 transition hover:text-slate-300",
                      active && "text-slate-300",
                      col.numeric && "ml-auto",
                    )}
                  >
                    {col.label}
                    {active ? (
                      sortDir === "asc" ? (
                        <ArrowUp size={11} />
                      ) : (
                        <ArrowDown size={11} />
                      )
                    ) : (
                      <ArrowUpDown size={11} className="opacity-40" />
                    )}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {sorted.map((row, i) => (
            <tr key={i} className="transition hover:bg-slate-800/30">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={clsx(
                    "px-5 py-3 text-slate-300",
                    col.numeric ? "text-right tabular-nums" : "text-left",
                    col.className,
                  )}
                >
                  {col.render
                    ? col.render(row)
                    : String((row as Record<string, unknown>)[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
      <div className="animate-pulse divide-y divide-slate-800/60">
        <div className="grid gap-4 px-5 py-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }).map((_, i) => (
            <div key={i} className="h-3 rounded bg-slate-800" />
          ))}
        </div>
        {Array.from({ length: 8 }).map((_, r) => (
          <div
            key={r}
            className="grid gap-4 px-5 py-4"
            style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: cols }).map((_, c) => (
              <div key={c} className="h-3 rounded bg-slate-800/70" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyTableState({ propertyId, label }: { propertyId: number; label: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900 px-6 py-10 text-center">
      <p className="mb-2 text-sm font-medium text-slate-300">{label}</p>
      <p className="mb-4 text-xs text-slate-500">
        Sync GSC data from Settings to populate this table, or try a wider date range.
      </p>
      <Link
        href={`/properties/${propertyId}/settings` as Route}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-500 hover:text-brand-600"
      >
        Open settings
        <ExternalLink size={12} />
      </Link>
    </div>
  );
}

// ─── Tab contents ─────────────────────────────────────────────────────────────

function QueriesTab({ propertyId, range }: { propertyId: number; range: DateRange }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["search-queries", propertyId, range.start, range.end],
    queryFn: () =>
      searchApi.getQueries(propertyId, { start: range.start, end: range.end, limit: 50 }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  if (isLoading) return <TableSkeleton cols={5} />;
  if (isError) return <ErrorBanner message={(error as Error).message} />;
  if (!data || data.length === 0)
    return <EmptyTableState propertyId={propertyId} label="No queries for this period" />;

  const columns: ColumnDef<SearchQuery>[] = [
    {
      key: "query",
      label: "Query",
      render: (row) => (
        <span className="font-medium text-slate-200">{row.query}</span>
      ),
    },
    {
      key: "clicks",
      label: "Clicks",
      numeric: true,
      render: (row) => fmtNumber(row.clicks),
    },
    {
      key: "impressions",
      label: "Impressions",
      numeric: true,
      render: (row) => fmtNumber(row.impressions),
    },
    {
      key: "ctr",
      label: "CTR",
      numeric: true,
      render: (row) => fmtCTR(row.ctr),
    },
    {
      key: "position",
      label: "Position",
      numeric: true,
      render: (row) => fmtPosition(row.position),
    },
  ];

  return <SortableTable rows={data} columns={columns} defaultSort="clicks" />;
}

function PagesTab({ propertyId, range }: { propertyId: number; range: DateRange }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["search-pages", propertyId, range.start, range.end],
    queryFn: () =>
      searchApi.getPages(propertyId, { start: range.start, end: range.end, limit: 50 }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  if (isLoading) return <TableSkeleton cols={5} />;
  if (isError) return <ErrorBanner message={(error as Error).message} />;
  if (!data || data.length === 0)
    return <EmptyTableState propertyId={propertyId} label="No pages for this period" />;

  const columns: ColumnDef<SearchPage>[] = [
    {
      key: "page",
      label: "Page",
      render: (row) => (
        <span
          className="block max-w-md truncate text-xs text-slate-400"
          title={row.page}
        >
          {truncateUrl(row.page, 80)}
        </span>
      ),
    },
    {
      key: "clicks",
      label: "Clicks",
      numeric: true,
      render: (row) => fmtNumber(row.clicks),
    },
    {
      key: "impressions",
      label: "Impressions",
      numeric: true,
      render: (row) => fmtNumber(row.impressions),
    },
    {
      key: "ctr",
      label: "CTR",
      numeric: true,
      render: (row) => fmtCTR(row.ctr),
    },
    {
      key: "position",
      label: "Position",
      numeric: true,
      render: (row) => fmtPosition(row.position),
    },
  ];

  return <SortableTable rows={data} columns={columns} defaultSort="clicks" />;
}

function OpportunitiesTab({
  propertyId,
  range,
}: {
  propertyId: number;
  range: DateRange;
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["search-opportunities", propertyId, range.start, range.end],
    queryFn: () =>
      searchApi.getOpportunities(propertyId, { start: range.start, end: range.end }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  if (isLoading) return <TableSkeleton cols={6} />;
  if (isError) return <ErrorBanner message={(error as Error).message} />;
  if (!data || data.length === 0)
    return (
      <EmptyTableState
        propertyId={propertyId}
        label="No rank-up opportunities for this period"
      />
    );

  const columns: ColumnDef<SearchOpportunity>[] = [
    {
      key: "query",
      label: "Query",
      render: (row) => (
        <span className="font-medium text-slate-200">{row.query}</span>
      ),
    },
    {
      key: "page",
      label: "Page",
      render: (row) => (
        <span
          className="block max-w-xs truncate text-xs text-slate-400"
          title={row.page}
        >
          {truncateUrl(row.page, 60)}
        </span>
      ),
    },
    {
      key: "position",
      label: "Position",
      numeric: true,
      render: (row) => fmtPosition(row.position),
    },
    {
      key: "impressions",
      label: "Impressions",
      numeric: true,
      render: (row) => fmtNumber(row.impressions),
    },
    {
      key: "ctr",
      label: "CTR",
      numeric: true,
      render: (row) => fmtCTR(row.ctr),
    },
    {
      key: "clicks",
      label: "Potential",
      numeric: true,
      render: (row) => <RankUpIndicator opportunity={row} />,
    },
  ];

  return (
    <SortableTable rows={data} columns={columns} defaultSort="impressions" />
  );
}

function RankUpIndicator({ opportunity }: { opportunity: SearchOpportunity }) {
  // Simple heuristic: more impressions and closer-to-page-1 = higher potential.
  // Score in 1..3 just for visual signal — backend can replace later.
  const positionScore = opportunity.position <= 8 ? 3 : opportunity.position <= 14 ? 2 : 1;
  const impressionScore =
    opportunity.impressions >= 5000 ? 3 : opportunity.impressions >= 1000 ? 2 : 1;
  const score = Math.min(3, Math.round((positionScore + impressionScore) / 2));

  const tone =
    score === 3
      ? "bg-green-500/15 text-green-400 border-green-500/30"
      : score === 2
      ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
      : "bg-slate-800 text-slate-400 border-slate-700";

  const label = score === 3 ? "High" : score === 2 ? "Medium" : "Low";

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
        tone,
      )}
    >
      <TrendingUp size={11} />
      {label}
    </span>
  );
}

// ─── Skeletons & banners ──────────────────────────────────────────────────────

function OverviewSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 rounded-xl bg-slate-800" />
        ))}
      </div>
      <div className="h-64 rounded-xl bg-slate-800" />
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-800 bg-red-950 p-4 text-sm text-red-400">
      Failed to load search data: {message}
    </div>
  );
}

function GSCNotLinkedCTA() {
  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
        <h3 className="mb-2 text-lg font-semibold text-white">
          Search Console not linked yet
        </h3>
        <p className="mb-6 text-sm text-slate-400">
          Connect Google Search Console to track clicks, impressions, CTR and
          rank-up opportunities for this property.
        </p>
        <Link
          href={"/properties" as Route}
          className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          Connect Google Search Console
          <ExternalLink size={12} />
        </Link>
      </div>
    </div>
  );
}

// ─── Search-type totals row ──────────────────────────────────────────────────

const SEARCH_TYPE_LABEL: Record<SearchTypeTab, string> = {
  web: "Web",
  image: "Image",
  video: "Video",
  news: "News",
  googleNews: "Google News",
  discover: "Discover",
};

function SearchTypeKPIRow({
  row,
  tab,
}: {
  row: SearchTypeBreakdownItem | null;
  tab: SearchTypeTab;
}) {
  const label = SEARCH_TYPE_LABEL[tab] ?? tab;
  if (!row) {
    return (
      <div className="mb-4 rounded-xl border border-dashed border-slate-800 bg-slate-900/40 px-4 py-3 text-xs text-slate-500">
        No <span className="font-medium text-slate-400">{label}</span> data for this period.
      </div>
    );
  }
  return (
    <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <SearchTypeMiniCard label={`${label} clicks`} value={fmtNumber(row.clicks)} />
      <SearchTypeMiniCard
        label={`${label} impressions`}
        value={fmtNumber(row.impressions)}
      />
      <SearchTypeMiniCard label={`${label} CTR`} value={fmtCTR(row.ctr)} />
      <SearchTypeMiniCard
        label={`${label} avg position`}
        value={fmtPosition(row.position)}
      />
    </div>
  );
}

function SearchTypeMiniCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </p>
      <p className="text-xl font-bold text-white">{value}</p>
    </div>
  );
}
