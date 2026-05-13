"use client";

import { useMemo } from "react";
import { Activity } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  searchWidgetsApi,
  type AppearanceBreakdownItem,
} from "@/lib/api-client";
import { formatNumber } from "@/lib/format";

interface AppearanceBreakdownProps {
  propertyId: number;
  start: string;
  end: string;
}

function fmtCTR(value: number): string {
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(2)}%`;
}

export function AppearanceBreakdown({
  propertyId,
  start,
  end,
}: AppearanceBreakdownProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["search-appearance", propertyId, start, end],
    queryFn: () => searchWidgetsApi.getAppearance(propertyId, { start, end }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  const sorted = useMemo<AppearanceBreakdownItem[]>(() => {
    if (!data) return [];
    return [...data].sort((a, b) => b.impressions - a.impressions);
  }, [data]);

  const hasAnyImpressions = sorted.some((r) => r.impressions > 0);

  // Multi-property rule: don't render the section at all when no impressions exist.
  // Loading / error still render so users see status.
  if (data && !hasAnyImpressions) {
    return null;
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center gap-3">
        <Activity className="h-4 w-4 text-slate-400" />
        <div>
          <h3 className="text-sm font-semibold text-white">Search Appearance</h3>
          <p className="text-xs text-slate-500">
            Rich-result and feature visibility in Google search
          </p>
        </div>
      </div>

      {isLoading && (
        <div
          className="animate-pulse rounded-lg border border-slate-800 bg-slate-900/40"
          style={{ height: 240 }}
          aria-hidden
        />
      )}
      {isError && (
        <div className="rounded-lg border border-red-900 bg-red-950/60 px-4 py-3 text-xs text-red-300">
          Failed to load: {(error as Error | undefined)?.message ?? "Unknown error"}
        </div>
      )}
      {data && hasAnyImpressions && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="min-h-[260px]">
            <ResponsiveContainer
              width="100%"
              height={Math.max(260, sorted.length * 36)}
            >
              <BarChart
                data={sorted}
                layout="vertical"
                margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#1e293b"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: number) =>
                    v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)
                  }
                />
                <YAxis
                  type="category"
                  dataKey="search_appearance"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={140}
                />
                <Tooltip
                  cursor={{ fill: "rgba(99,102,241,0.08)" }}
                  contentStyle={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                    borderRadius: 8,
                  }}
                  labelStyle={{ color: "#94a3b8", fontSize: 12 }}
                  itemStyle={{ color: "#e2e8f0", fontSize: 12 }}
                  formatter={(value: number) => [
                    formatNumber(value),
                    "Impressions",
                  ]}
                />
                <Bar dataKey="impressions" fill="#22d3ee" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="pb-2 pr-4 text-left text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Appearance
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Clicks
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Impr.
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    CTR
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Position
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {sorted.map((row) => (
                  <tr
                    key={row.search_appearance}
                    className="hover:bg-slate-800/30"
                  >
                    <td className="pr-4 py-2.5 text-left">
                      <span
                        className="block max-w-[180px] truncate text-slate-300"
                        title={row.search_appearance}
                      >
                        {row.search_appearance}
                      </span>
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-300">
                      {formatNumber(row.clicks)}
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-300">
                      {formatNumber(row.impressions)}
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-400">
                      {fmtCTR(row.ctr)}
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-400">
                      {row.position.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * Empty-state variant rendered by the page when the query returns zero rows.
 * Kept as a separate export so the page can decide whether to show the
 * "may not be eligible" copy or hide the section entirely.
 */
export function AppearanceEmpty() {
  return (
    <section className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-5">
      <div className="mb-2 flex items-center gap-3">
        <Activity className="h-4 w-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-300">Search Appearance</h3>
      </div>
      <p className="text-xs text-slate-500">
        No rich-result data for this period — your site may not be eligible for
        these features yet.
      </p>
    </section>
  );
}
