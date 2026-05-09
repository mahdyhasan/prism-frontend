"use client";

import { clsx } from "clsx";

export type DatePreset = "last_7d" | "last_30d" | "last_90d" | "last_12m" | "last_14m";
export type CompareTo = "previous_period" | "same_period_last_year" | "none";

const presets: { value: DatePreset; label: string }[] = [
  { value: "last_7d", label: "7 days" },
  { value: "last_30d", label: "30 days" },
  { value: "last_90d", label: "90 days" },
  { value: "last_12m", label: "12 months" },
  { value: "last_14m", label: "14 months" },
];

const compareOptions: { value: CompareTo; label: string }[] = [
  { value: "none", label: "No comparison" },
  { value: "previous_period", label: "vs previous period" },
  { value: "same_period_last_year", label: "vs same period last year" },
];

interface DateRangePickerProps {
  preset: DatePreset;
  compareTo: CompareTo;
  onPresetChange: (p: DatePreset) => void;
  onCompareChange: (c: CompareTo) => void;
}

export function DateRangePicker({
  preset,
  compareTo,
  onPresetChange,
  onCompareChange,
}: DateRangePickerProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center rounded-lg border border-slate-700 bg-slate-900 p-0.5">
        {presets.map((p) => (
          <button
            key={p.value}
            onClick={() => onPresetChange(p.value)}
            className={clsx(
              "rounded-md px-3 py-1.5 text-xs font-medium transition",
              preset === p.value
                ? "bg-brand-600 text-white"
                : "text-slate-400 hover:text-white",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>
      <select
        value={compareTo}
        onChange={(e) => onCompareChange(e.target.value as CompareTo)}
        className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-400 focus:border-slate-600 focus:outline-none"
      >
        {compareOptions.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
