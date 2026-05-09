"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyPoint } from "@/lib/api-client";

interface SessionsChartProps {
  data: DailyPoint[];
}

export function SessionsChart({ data }: SessionsChartProps) {
  if (data.length === 0) {
    return <EmptyState label="No session data for this period." />;
  }

  const formatted = data.map((d) => ({
    date: d.date.slice(5), // MM-DD
    sessions: d.sessions,
    users: d.users,
  }));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">Sessions trend</h3>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={formatted} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="sessGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
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
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
            width={40}
          />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
            labelStyle={{ color: "#94a3b8", fontSize: 12 }}
            itemStyle={{ color: "#e2e8f0", fontSize: 12 }}
          />
          <Area
            type="monotone"
            dataKey="sessions"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#sessGrad)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex h-48 items-center justify-center rounded-xl border border-slate-800 bg-slate-900">
      <p className="text-sm text-slate-600">{label}</p>
    </div>
  );
}
