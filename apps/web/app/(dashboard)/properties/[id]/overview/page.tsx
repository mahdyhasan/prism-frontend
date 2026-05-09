"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { KPICard } from "@/components/dashboard/kpi-card";
import { SessionsChart } from "@/components/dashboard/sessions-chart";
import { DevicesChart } from "@/components/dashboard/devices-chart";
import { TopTable } from "@/components/dashboard/top-table";
import {
  DateRangePicker,
  type DatePreset,
  type CompareTo,
} from "@/components/dashboard/date-range-picker";
import { useOverview } from "@/hooks/use-overview";
import type { LandingPageRow, TrafficSourceRow } from "@/lib/api-client";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);
  const [preset, setPreset] = useState<DatePreset>("last_30d");
  const [compareTo, setCompareTo] = useState<CompareTo>("previous_period");

  const { data, isLoading, isError, error } = useOverview(propertyId, preset, compareTo);

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
          {/* Date range controls */}
          <div className="mb-6 flex items-center justify-between">
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

          {isLoading && <LoadingSkeleton />}
          {isError && <ErrorBanner message={(error as Error).message} />}

          {data && (
            <>
              {/* KPI cards */}
              <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                <KPICard label="Sessions" data={data.kpis.sessions} />
                <KPICard label="Users" data={data.kpis.users} />
                <KPICard label="New users" data={data.kpis.new_users} />
                <KPICard
                  label="Engagement rate"
                  data={data.kpis.engagement_rate}
                  format="percent"
                />
                <KPICard
                  label="Bounce rate"
                  data={data.kpis.bounce_rate}
                  format="percent"
                />
                <KPICard label="Conversions" data={data.kpis.conversions} />
                <KPICard
                  label="Revenue"
                  data={data.kpis.total_revenue}
                  format="currency"
                />
              </div>

              {/* Sessions trend + Devices */}
              <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
                <div className="lg:col-span-2">
                  <SessionsChart data={data.sessions_trend} />
                </div>
                <DevicesChart data={data.devices} />
              </div>

              {/* Tables */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <TopTable<LandingPageRow>
                  title="Top landing pages"
                  rows={data.top_landing_pages}
                  columns={[
                    {
                      key: "landing_page",
                      label: "Page",
                      render: (v) => (
                        <span className="max-w-xs truncate block text-xs text-slate-400">
                          {String(v)}
                        </span>
                      ),
                    },
                    { key: "sessions", label: "Sessions" },
                    { key: "conversions", label: "Conv." },
                    {
                      key: "bounce_rate",
                      label: "Bounce",
                      render: (v) => `${(Number(v) * 100).toFixed(0)}%`,
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
                      render: (v, row) => (
                        <span className="text-xs text-slate-400">
                          {String(v)} / {String(row.medium)}
                        </span>
                      ),
                    },
                    { key: "sessions", label: "Sessions" },
                    { key: "users", label: "Users" },
                    { key: "conversions", label: "Conv." },
                  ]}
                />
              </div>
            </>
          )}

          {/* Empty state: no data yet */}
          {!isLoading && !isError && data && data.sessions_trend.length === 0 && (
            <div className="mt-8 text-center">
              <p className="text-sm text-slate-500">
                No data for this period. Run a sync or adjust the date range.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-24 rounded-xl bg-slate-800" />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 h-56 rounded-xl bg-slate-800" />
        <div className="h-56 rounded-xl bg-slate-800" />
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-800 bg-red-950 p-4 text-sm text-red-400">
      Failed to load overview data: {message}
    </div>
  );
}
