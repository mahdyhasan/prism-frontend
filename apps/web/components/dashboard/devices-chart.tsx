"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Legend } from "recharts";
import type { DeviceRow } from "@/lib/api-client";

const COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981"];

interface DevicesChartProps {
  data: DeviceRow[];
}

export function DevicesChart({ data }: DevicesChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-slate-800 bg-slate-900">
        <p className="text-sm text-slate-600">No device data for this period.</p>
      </div>
    );
  }

  const chartData = data.map((d) => ({
    name: d.device_category.charAt(0).toUpperCase() + d.device_category.slice(1),
    value: d.sessions,
  }));

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">Sessions by device</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={2}
            dataKey="value"
          >
            {chartData.map((_, index) => (
              <Cell key={index} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
            itemStyle={{ color: "#e2e8f0", fontSize: 12 }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, color: "#94a3b8" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
