"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Layers } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  overviewWidgetsApi,
  type ChannelBreakdownItem,
} from "@/lib/api-client";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";

interface ChannelBreakdownProps {
  propertyId: number;
  start: string;
  end: string;
  currency?: string;
}

export function ChannelBreakdown({
  propertyId,
  start,
  end,
  currency = "USD",
}: ChannelBreakdownProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["overview-channels", propertyId, start, end],
    queryFn: () => overviewWidgetsApi.getChannels(propertyId, { start, end }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });

  const sorted = useMemo<ChannelBreakdownItem[]>(() => {
    if (!data) return [];
    return [...data].sort((a, b) => b.sessions - a.sessions);
  }, [data]);

  const totalSessions = useMemo(
    () => sorted.reduce((sum, r) => sum + r.sessions, 0),
    [sorted],
  );

  const showRevenue = useMemo(
    () => sorted.some((r) => r.revenue > 0),
    [sorted],
  );

  return (
    <Section
      title="Channels"
      subtitle="Where your traffic comes from"
      icon={<Layers className="h-4 w-4 text-slate-400" />}
    >
      {isLoading && <SectionSkeleton height={280} />}
      {isError && (
        <SectionError
          message={(error as Error | undefined)?.message ?? "Unknown error"}
        />
      )}
      {data && (totalSessions === 0 || sorted.length === 0) && (
        <SectionEmpty message="No channel data for this period" />
      )}
      {data && totalSessions > 0 && sorted.length > 0 && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="min-h-[280px]">
            <ResponsiveContainer width="100%" height={Math.max(280, sorted.length * 32)}>
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
                  dataKey="channel_group"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={110}
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
                  formatter={(value: number) => [formatNumber(value), "Sessions"]}
                />
                <Bar dataKey="sessions" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="pb-2 pr-4 text-left text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Channel
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Sessions
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Share
                  </th>
                  <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Conv.
                  </th>
                  {showRevenue && (
                    <th className="pb-2 pl-4 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                      Revenue
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {sorted.map((row) => (
                  <tr key={row.channel_group} className="hover:bg-slate-800/30">
                    <td className="pr-4 py-2.5 text-left">
                      <span
                        className="block max-w-[160px] truncate text-slate-300"
                        title={row.channel_group}
                      >
                        {row.channel_group}
                      </span>
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-300">
                      {formatNumber(row.sessions)}
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-400">
                      {formatPercent(row.share)}
                    </td>
                    <td className="pl-4 py-2.5 text-right tabular-nums text-slate-300">
                      {formatNumber(row.conversions)}
                    </td>
                    {showRevenue && (
                      <td className="pl-4 py-2.5 text-right tabular-nums text-slate-300">
                        {formatCurrency(row.revenue, currency)}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Section>
  );
}

function Section({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center gap-3">
        {icon}
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

function SectionSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div
      className={clsx(
        "animate-pulse rounded-lg border border-slate-800 bg-slate-900/40",
      )}
      style={{ height }}
      aria-hidden
    />
  );
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-900 bg-red-950/60 px-4 py-3 text-xs text-red-300">
      Failed to load: {message}
    </div>
  );
}

function SectionEmpty({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-10 text-center text-xs text-slate-500">
      {message}
    </div>
  );
}
