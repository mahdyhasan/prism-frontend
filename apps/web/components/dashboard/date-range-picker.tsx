"use client";

import { clsx } from "clsx";

export type DatePreset = "last_7d" | "last_30d" | "last_90d" | "last_12m" | "last_14m";
export type CompareTo = "previous_period" | "same_period_last_year" | "none";

const presets: { value: DatePreset; label: string }[] = [
  { value: "last_7d", label: "7d" },
  { value: "last_30d", label: "28d" },
  { value: "last_90d", label: "90d" },
  { value: "last_12m", label: "12m" },
  { value: "last_14m", label: "14m" },
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
  const compareEnabled = compareTo !== "none";

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div
        role="tablist"
        aria-label="Date range"
        className="flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5"
      >
        {presets.map((p) => {
          const active = preset === p.value;
          return (
            <button
              key={p.value}
              role="tab"
              aria-selected={active}
              onClick={() => onPresetChange(p.value)}
              className={clsx(
                "rounded-md px-3 py-1.5 text-xs font-medium transition",
                active
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white",
              )}
            >
              {p.label}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={compareEnabled}
        onClick={() => onCompareChange(compareEnabled ? "none" : "previous_period")}
        className={clsx(
          "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
          compareEnabled
            ? "border-brand-500 bg-brand-600/10 text-white"
            : "border-slate-800 bg-slate-900 text-slate-400 hover:text-white",
        )}
      >
        <span
          className={clsx(
            "relative inline-block h-3.5 w-7 rounded-full transition",
            compareEnabled ? "bg-brand-500" : "bg-slate-700",
          )}
        >
          <span
            className={clsx(
              "absolute top-0.5 h-2.5 w-2.5 rounded-full bg-white transition-all",
              compareEnabled ? "left-3.5" : "left-0.5",
            )}
          />
        </span>
        Compare to previous period
      </button>
    </div>
  );
}
