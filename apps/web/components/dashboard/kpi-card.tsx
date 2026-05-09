import { clsx } from "clsx";
import type { KPIValue } from "@/lib/api-client";

interface KPICardProps {
  label: string;
  data: KPIValue;
  format?: "number" | "percent" | "currency" | "duration";
}

function fmt(value: number, format: KPICardProps["format"]) {
  if (format === "percent") return `${(value * 100).toFixed(1)}%`;
  if (format === "currency") return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (format === "duration") {
    const mins = Math.floor(value / 60);
    const secs = Math.floor(value % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  }
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}

export function KPICard({ label, data, format = "number" }: KPICardProps) {
  const delta = data.delta_percent;
  const positive = delta !== null && delta > 0;
  const negative = delta !== null && delta < 0;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-500">{label}</p>
      <p className="mb-2 text-3xl font-bold text-white">{fmt(data.value, format)}</p>
      {delta !== null && (
        <p
          className={clsx(
            "text-xs font-medium",
            positive && "text-green-400",
            negative && "text-red-400",
            !positive && !negative && "text-slate-500",
          )}
        >
          {positive ? "▲" : negative ? "▼" : "—"}{" "}
          {Math.abs(delta).toFixed(1)}% vs previous
        </p>
      )}
    </div>
  );
}
