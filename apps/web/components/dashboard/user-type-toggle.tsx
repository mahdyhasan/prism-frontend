"use client";

import { clsx } from "clsx";
import { Users } from "lucide-react";

export type UserTypeFilter = "all" | "new" | "returning";

interface UserTypeToggleProps {
  value: UserTypeFilter;
  onChange: (v: UserTypeFilter) => void;
  /** When true, the segment is disabled (no data) */
  newDisabled?: boolean;
  returningDisabled?: boolean;
}

const OPTIONS: { value: UserTypeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "new", label: "New" },
  { value: "returning", label: "Returning" },
];

export function UserTypeToggle({
  value,
  onChange,
  newDisabled = false,
  returningDisabled = false,
}: UserTypeToggleProps) {
  return (
    <div className="inline-flex items-center gap-2">
      <Users className="h-3.5 w-3.5 text-slate-500" />
      <span className="text-xs font-medium uppercase tracking-widest text-slate-500">
        User type
      </span>
      <div
        role="tablist"
        aria-label="User type filter"
        className="inline-flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5"
      >
        {OPTIONS.map((opt) => {
          const disabled =
            (opt.value === "new" && newDisabled) ||
            (opt.value === "returning" && returningDisabled);
          const active = value === opt.value;
          const display = disabled ? "—" : opt.label;
          return (
            <button
              key={opt.value}
              role="tab"
              type="button"
              aria-selected={active}
              disabled={disabled}
              onClick={() => onChange(opt.value)}
              title={
                disabled
                  ? `No ${opt.value} user data for this period`
                  : undefined
              }
              className={clsx(
                "rounded-md px-3 py-1 text-xs font-medium transition",
                active && !disabled && "bg-brand-600 text-white shadow-sm",
                !active && !disabled && "text-slate-400 hover:text-white",
                disabled && "cursor-not-allowed text-slate-600",
              )}
            >
              {opt.value === "all" ? opt.label : display}
            </button>
          );
        })}
      </div>
    </div>
  );
}
