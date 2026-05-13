"use client";

import { clsx } from "clsx";
import type { SearchType } from "@/lib/api-client";

export type SearchTypeTab = SearchType;

interface SearchTypeTabsProps {
  value: SearchTypeTab;
  onChange: (v: SearchTypeTab) => void;
  /** Map of search_type → has data. Tabs without data are dimmed but still clickable. */
  available?: Partial<Record<SearchType, boolean>>;
}

const TABS: { value: SearchType; label: string }[] = [
  { value: "web", label: "Web" },
  { value: "image", label: "Image" },
  { value: "video", label: "Video" },
  { value: "news", label: "News" },
  { value: "discover", label: "Discover" },
];

export function SearchTypeTabs({
  value,
  onChange,
  available,
}: SearchTypeTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Search type"
      className="inline-flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5"
    >
      {TABS.map((t) => {
        const active = value === t.value;
        const hasData = available ? available[t.value] !== false : true;
        return (
          <button
            key={t.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={clsx(
              "rounded-md px-3 py-1.5 text-xs font-medium transition",
              active
                ? "bg-brand-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white",
              !hasData && !active && "opacity-50",
            )}
            title={hasData ? undefined : "No data for this search type"}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
