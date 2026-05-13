// Phase 1 polish: loading/empty/error states + delta indicators
"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ExternalLink, Inbox, RefreshCw } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { KPICard } from "@/components/dashboard/kpi-card";
import { SessionsChart } from "@/components/dashboard/sessions-chart";
import { DevicesChart } from "@/components/dashboard/devices-chart";
import { TopTable } from "@/components/dashboard/top-table";
import { ChannelBreakdown } from "@/components/dashboard/channel-breakdown";
import { HourlyHeatmap } from "@/components/dashboard/hourly-heatmap";
import {
  UserTypeToggle,
  type UserTypeFilter,
} from "@/components/dashboard/user-type-toggle";
import {
  DateRangePicker,
  type DatePreset,
  type CompareTo,
} from "@/components/dashboard/date-range-picker";
import { useOverview } from "@/hooks/use-overview";
import { useProperty } from "@/hooks/use-properties";
import {
  formatNumber,
  formatPercent,
} from "@/lib/format";
import {
  overviewWidgetsApi,
  type KPIValue,
  type LandingPageRow,
  type OverviewResponse,
  type TrafficSourceRow,
} from "@/lib/api-client";
import { hasEcommerceData, isGA4Linked } from "@/lib/property-features";

const DEFAULT_CURRENCY = "USD";

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

/**
 * Build a KPIValue for the segmented (sessions/users/engaged-sessions) KPIs.
 * When `segmentValue` is undefined we keep the original KPI (with deltas).
 * When a segment is active we replace the value and clear deltas — the
 * contract doesn't include segment-level deltas.
 */
function buildSegmentKPI(
  base: KPIValue,
  segmentValue: number | undefined,
): KPIValue {
  if (segmentValue === undefined) return base;
  return {
    value: segmentValue,
    previous_value: null,
    delta_percent: null,
  };
}

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const [preset, setPreset] = useState<DatePreset>("last_30d");
  const [compareTo, setCompareTo] = useState<CompareTo>("previous_period");
  const [userType, setUserType] = useState<UserTypeFilter>("all");

  const { data: property } = useProperty(propertyId);
  const ga4Linked = property ? isGA4Linked(property) : true;

  const { data, isLoading, isError, error, refetch, isFetching } = useOverview(
    propertyId,
    preset,
    compareTo,
  );

  // Date range for widgets that take explicit start/end. Prefer dates the
  // overview backend echoed back; fall back to local computation.
  const { start, end } = useMemo(() => {
    if (data?.start_date && data?.end_date) {
      return { start: data.start_date, end: data.end_date };
    }
    return rangeFor(preset);
  }, [data?.start_date, data?.end_date, preset]);

  const userTypeQuery = useQuery({
    queryKey: ["overview-user-type", propertyId, start, end],
    queryFn: () => overviewWidgetsApi.getUserType(propertyId, { start, end }),
    enabled: !!propertyId && !!start && !!end && ga4Linked,
    staleTime: 1000 * 60 * 5,
  });

  const showDelta = compareTo !== "none";
  const currency = DEFAULT_CURRENCY;
  const isEmpty = data ? isOverviewEmpty(data) : false;
  const ecommerce = data ? hasEcommerceData(data.kpis) : false;

  const userTypeData = userTypeQuery.data ?? null;
  const newDisabled = !userTypeData || !userTypeData.new;
  const returningDisabled = !userTypeData || !userTypeData.returning;

  const segmentStats = useMemo(() => {
    if (!userTypeData) return null;
    if (userType === "new") return userTypeData.new;
    if (userType === "returning") return userTypeData.returning;
    return userTypeData.total;
  }, [userTypeData, userType]);

  // Segmented KPIs: only override value when a non-"all" segment is selected
  // AND the segment exists. The third tile re-labels to "Engaged sessions"
  // when a segment is active, otherwise stays as "New users".
  const segmentActive = userType !== "all" && !!segmentStats;
  const sessionsKPIData = data
    ? buildSegmentKPI(data.kpis.sessions, segmentActive ? segmentStats!.sessions : undefined)
    : null;
  const usersKPIData = data
    ? buildSegmentKPI(data.kpis.users, segmentActive ? segmentStats!.users : undefined)
    : null;
  const thirdKPIData = data
    ? buildSegmentKPI(
        data.kpis.new_users,
        segmentActive ? segmentStats!.engaged_sessions : undefined,
      )
    : null;
  const thirdKPILabel = segmentActive ? "Engaged sessions" : "New users";

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header
          title="Overview"
          propertyId={propertyId}
          lastSynced={data?.last_synced_at ?? null}
        />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              {data && (
                <p className="text-xs text-slate-500">
                  {data.start_date} — {data.end_date}
                </p>
              )}
            </div>
            <DateRangePicker
              preset={preset}
              compareTo={compareTo}
              onPresetChange={setPreset}
              onCompareChange={setCompareTo}
            />
          </div>

          {property && !ga4Linked && (
            <NotLinkedCTA
              title="GA4 not linked yet"
              description="Connect your Google Analytics 4 property to start seeing traffic, engagement and conversion data here."
              cta="Manage properties"
              href={"/properties" as Route}
            />
          )}

          {ga4Linked && isError && (
            <ErrorBanner
              message={(error as Error).message}
              onRetry={() => void refetch()}
              retrying={isFetching}
            />
          )}

          {ga4Linked && isLoading && <LoadingSkeleton />}

          {ga4Linked && data && sessionsKPIData && usersKPIData && thirdKPIData && (
            <>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <UserTypeToggle
                  value={userType}
                  onChange={setUserType}
                  newDisabled={newDisabled}
                  returningDisabled={returningDisabled}
                />
              </div>

              <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                <KPICard
                  label="Sessions"
                  data={sessionsKPIData}
                  directionOfGood="up"
                  showDelta={showDelta && !segmentActive}
                  currency={currency}
                />
                <KPICard
                  label="Users"
                  data={usersKPIData}
                  directionOfGood="up"
                  showDelta={showDelta && !segmentActive}
                  currency={currency}
                />
                <KPICard
                  label={thirdKPILabel}
                  data={thirdKPIData}
                  directionOfGood="up"
                  showDelta={showDelta && !segmentActive}
                  currency={currency}
                />
                <KPICard
                  label="Engagement rate"
                  data={data.kpis.engagement_rate}
                  format="percent"
                  directionOfGood="up"
                  showDelta={showDelta}
                  currency={currency}
                />
                <KPICard
                  label="Bounce rate"
                  data={data.kpis.bounce_rate}
                  format="percent"
                  directionOfGood="down"
                  showDelta={showDelta}
                  currency={currency}
                />
                <div
                  className={ecommerce ? undefined : "opacity-50"}
                  title={ecommerce ? undefined : "No e-commerce data for this period"}
                >
                  <KPICard
                    label="Conversions"
                    data={data.kpis.conversions}
                    directionOfGood="up"
                    showDelta={showDelta}
                    currency={currency}
                  />
                </div>
                <div
                  className={ecommerce ? undefined : "opacity-50"}
                  title={ecommerce ? undefined : "No e-commerce data for this period"}
                >
                  <KPICard
                    label="Revenue"
                    data={data.kpis.total_revenue}
                    format="currency"
                    directionOfGood="up"
                    showDelta={showDelta}
                    currency={currency}
                  />
                </div>
              </div>

              {isEmpty ? (
                <EmptyState onRefresh={() => void refetch()} refreshing={isFetching} />
              ) : (
                <>
                  <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <div className="lg:col-span-2">
                      <SessionsChart data={data.sessions_trend} />
                    </div>
                    <DevicesChart data={data.devices} />
                  </div>

                  <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <TopTable<LandingPageRow>
                      title="Top landing pages"
                      rows={data.top_landing_pages}
                      columns={[
                        {
                          key: "landing_page",
                          label: "Page",
                          render: (v) => {
                            const s = String(v);
                            return (
                              <span
                                title={s}
                                className="block max-w-xs truncate text-xs text-slate-400"
                              >
                                {s}
                              </span>
                            );
                          },
                        },
                        {
                          key: "sessions",
                          label: "Sessions",
                          align: "right",
                          render: (v) => formatNumber(Number(v)),
                        },
                        {
                          key: "conversions",
                          label: "Conv.",
                          align: "right",
                          render: (v) => formatNumber(Number(v)),
                        },
                        {
                          key: "bounce_rate",
                          label: "Bounce",
                          align: "right",
                          render: (v) => formatPercent(Number(v)),
                        },
                      ]}
                    />
                    <TopTable<TrafficSourceRow>
                      title="Top traffic sources"
                      rows={data.top_traffic_sources}
                      columns={[
                        {
                          key: "source",
                          label: "Source / Medium",
                          render: (v, row) => {
                            const label = `${String(v)} / ${String(row.medium)}`;
                            return (
                              <span
                                title={label}
                                className="block max-w-xs truncate text-xs text-slate-400"
                              >
                                {label}
                              </span>
                            );
                          },
                        },
                        {
                          key: "sessions",
                          label: "Sessions",
                          align: "right",
                          render: (v) => formatNumber(Number(v)),
                        },
                        {
                          key: "users",
                          label: "Users",
                          align: "right",
                          render: (v) => formatNumber(Number(v)),
                        },
                        {
                          key: "conversions",
                          label: "Conv.",
                          align: "right",
                          render: (v) => formatNumber(Number(v)),
                        },
                      ]}
                    />
                  </div>

                  {/* Tier 1 widgets */}
                  <div className="mb-6">
                    <ChannelBreakdown
                      propertyId={propertyId}
                      start={start}
                      end={end}
                      currency={currency}
                    />
                  </div>
                  <div className="mb-6">
                    <HourlyHeatmap
                      propertyId={propertyId}
                      start={start}
                      end={end}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

interface NotLinkedCTAProps {
  title: string;
  description: string;
  cta: string;
  href: Route;
}

function NotLinkedCTA({ title, description, cta, href }: NotLinkedCTAProps) {
  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
        <h3 className="mb-2 text-lg font-semibold text-white">{title}</h3>
        <p className="mb-6 text-sm text-slate-400">{description}</p>
        <Link
          href={href}
          className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          {cta}
          <ExternalLink size={12} />
        </Link>
      </div>
    </div>
  );
}

function isOverviewEmpty(data: OverviewResponse): boolean {
  const k = data.kpis;
  const allKpisZero =
    k.sessions.value === 0 &&
    k.users.value === 0 &&
    k.new_users.value === 0 &&
    k.conversions.value === 0 &&
    k.total_revenue.value === 0 &&
    k.engagement_rate.value === 0 &&
    k.bounce_rate.value === 0;
  const allArraysEmpty =
    data.sessions_trend.length === 0 &&
    data.top_landing_pages.length === 0 &&
    data.top_traffic_sources.length === 0 &&
    data.devices.length === 0;
  return allKpisZero || allArraysEmpty;
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-hidden>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="h-[108px] rounded-xl border border-slate-800 bg-slate-900"
          >
            <div className="space-y-3 p-5">
              <div className="h-3 w-20 rounded bg-slate-800" />
              <div className="h-7 w-24 rounded bg-slate-800" />
              <div className="h-3 w-16 rounded bg-slate-800" />
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-[280px] rounded-xl border border-slate-800 bg-slate-900 lg:col-span-2" />
        <div className="h-[280px] rounded-xl border border-slate-800 bg-slate-900" />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="h-[260px] rounded-xl border border-slate-800 bg-slate-900" />
        <div className="h-[260px] rounded-xl border border-slate-800 bg-slate-900" />
      </div>
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
            Failed to load overview data
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
        <RefreshCw className={`h-3 w-3 ${retrying ? "animate-spin" : ""}`} />
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}

interface EmptyStateProps {
  onRefresh: () => void;
  refreshing: boolean;
}

function EmptyState({ onRefresh, refreshing }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800/60 text-slate-400">
        <Inbox className="h-6 w-6" />
      </div>
      <h3 className="mb-1 text-sm font-semibold text-white">No data yet</h3>
      <p className="mx-auto mb-5 max-w-sm text-xs text-slate-400">
        Your first sync is still running. Check back in a few minutes.
      </p>
      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
        {refreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}
