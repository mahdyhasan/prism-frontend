"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { clsx } from "clsx";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  Construction,
  Download,
  Globe,
  LayoutDashboard,
  Lightbulb,
  Link2,
  Loader2,
  MonitorSmartphone,
  Search,
  Table as TableIcon,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import {
  DateRangePicker,
  type CompareTo,
  type DatePreset,
} from "@/components/dashboard/date-range-picker";
import {
  exportsApi,
  getStoredToken,
  type ExportKind,
} from "@/lib/api-client";
import { useProperty } from "@/hooks/use-properties";
import { isGSCLinked } from "@/lib/property-features";

// ── Date helpers (mirrors search page) ────────────────────────────────────────

const PRESET_DAYS: Record<DatePreset, number> = {
  last_7d: 7,
  last_30d: 30,
  last_90d: 90,
  last_12m: 365,
  last_14m: 425,
};

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function rangeFor(preset: DatePreset): { start: string; end: string } {
  const days = PRESET_DAYS[preset];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { start: toISO(start), end: toISO(end) };
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface StandardReport {
  title: string;
  description: string;
  href: (propertyId: number) => string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

interface ExportItem {
  kind: ExportKind;
  filenameBase: string; // e.g. "sessions" → prism_sessions_<start>_<end>.csv
  name: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

// ── Static config ─────────────────────────────────────────────────────────────

const STANDARD_REPORTS: StandardReport[] = [
  {
    title: "Traffic Overview",
    description: "Sessions, users, conversions and revenue at a glance.",
    href: (id) => `/properties/${id}/overview`,
    icon: LayoutDashboard,
  },
  {
    title: "Search Console",
    description: "Clicks, impressions, CTR and rank-up opportunities.",
    href: (id) => `/properties/${id}/search`,
    icon: Search,
  },
  {
    title: "AI Insights",
    description: "Anomalies, trends and decay surfaced by Claude.",
    href: (id) => `/properties/${id}/insights`,
    icon: Lightbulb,
  },
];

const EXPORTS: ExportItem[] = [
  {
    kind: "ga4_sessions",
    filenameBase: "sessions",
    name: "GA4 Sessions",
    description: "Daily sessions, users, conversions and revenue.",
    icon: BarChart3,
  },
  {
    kind: "ga4_pages",
    filenameBase: "pages",
    name: "GA4 Top Pages",
    description: "Sessions and conversions by landing page.",
    icon: TableIcon,
  },
  {
    kind: "ga4_sources",
    filenameBase: "sources",
    name: "GA4 Traffic Sources",
    description: "Sessions broken down by source / medium / campaign.",
    icon: Link2,
  },
  {
    kind: "ga4_devices",
    filenameBase: "devices",
    name: "GA4 Devices",
    description: "Sessions and conversions by device category.",
    icon: MonitorSmartphone,
  },
  {
    kind: "ga4_geo",
    filenameBase: "geo",
    name: "GA4 Geography",
    description: "Sessions and users by country / region.",
    icon: Globe,
  },
  {
    kind: "gsc_queries",
    filenameBase: "queries",
    name: "GSC Queries",
    description: "Clicks, impressions, CTR and position by query.",
    icon: Search,
  },
  {
    kind: "gsc_pages",
    filenameBase: "gsc_pages",
    name: "GSC Pages",
    description: "Clicks, impressions, CTR and position by page.",
    icon: TableIcon,
  },
];

// ── Download helper ───────────────────────────────────────────────────────────

interface BannerState {
  kind: "success" | "error";
  message: string;
}

async function downloadCsv(path: string, filename: string): Promise<void> {
  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const url = `${exportsApi.apiBase}${path}`;
  const r = await fetch(url, { headers });
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`HTTP ${r.status}: ${text || r.statusText}`);
  }
  const blob = await r.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const { id } = useParams<{ id: string }>();
  const propertyId = Number(id);

  const [preset, setPreset] = useState<DatePreset>("last_30d");
  const [compareTo, setCompareTo] = useState<CompareTo>("none");
  const [activeKind, setActiveKind] = useState<ExportKind | null>(null);
  const [banner, setBanner] = useState<BannerState | null>(null);

  const { data: property } = useProperty(propertyId);
  const gscLinked = property ? isGSCLinked(property) : true;

  const range = useMemo(() => rangeFor(preset), [preset]);

  function isGscKind(kind: ExportKind): boolean {
    return kind.startsWith("gsc_");
  }

  async function handleDownload(item: ExportItem) {
    if (activeKind) return;
    if (isGscKind(item.kind) && !gscLinked) return;
    setActiveKind(item.kind);
    setBanner(null);
    const filename = `prism_${item.filenameBase}_${range.start}_${range.end}.csv`;
    try {
      const path = exportsApi.path(propertyId, item.kind, range);
      await downloadCsv(path, filename);
      setBanner({ kind: "success", message: `Downloaded ${filename}` });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Download failed";
      setBanner({ kind: "error", message: `Failed to download ${filename}: ${message}` });
    } finally {
      setActiveKind(null);
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title="Reports" propertyId={propertyId} lastSynced={null} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm text-slate-400">
                Standard reports and data exports
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {range.start} — {range.end}
              </p>
            </div>
            <DateRangePicker
              preset={preset}
              compareTo={compareTo}
              onPresetChange={setPreset}
              onCompareChange={setCompareTo}
            />
          </div>

          <Section
            title="Standard reports"
            subtitle="Curated dashboards for the most common analytics workflows."
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {STANDARD_REPORTS.map((report) => (
                <ReportCard key={report.title} report={report} propertyId={propertyId} />
              ))}
            </div>
          </Section>

          <Section
            title="Data exports"
            subtitle="Download raw warehouse data as CSV for the selected date range."
          >
            {banner && <Banner state={banner} onDismiss={() => setBanner(null)} />}

            <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-widest text-slate-500">
                      Dataset
                    </th>
                    <th className="hidden px-5 py-3 text-left text-xs font-semibold uppercase tracking-widest text-slate-500 md:table-cell">
                      Description
                    </th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-widest text-slate-500">
                      &nbsp;
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {EXPORTS.map((item) => {
                    const gscBlocked = isGscKind(item.kind) && !gscLinked;
                    return (
                      <ExportRow
                        key={item.kind}
                        item={item}
                        busy={activeKind === item.kind}
                        disabled={
                          gscBlocked ||
                          (activeKind !== null && activeKind !== item.kind)
                        }
                        disabledReason={
                          gscBlocked ? "GSC not linked for this property" : undefined
                        }
                        onDownload={() => handleDownload(item)}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            title="Custom report builder"
            subtitle="Build your own reports by mixing dimensions and metrics."
          >
            <div className="flex items-start gap-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
                <Construction size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-200">
                  Coming in Phase 5
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  A drag-and-drop report builder is on the way. For now, use the
                  data exports above to pull raw CSVs into your own analysis tools.
                </p>
              </div>
            </div>
          </Section>
        </main>
      </div>
    </div>
  );
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <div className="mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">
          {title}
        </h2>
        {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function ReportCard({
  report,
  propertyId,
}: {
  report: StandardReport;
  propertyId: number;
}) {
  const Icon = report.icon;
  return (
    <Link
      href={report.href(propertyId) as Route}
      className="group flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5 transition hover:border-brand-500"
    >
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-slate-300 transition group-hover:bg-brand-600/20 group-hover:text-brand-400">
        <Icon size={18} />
      </div>
      <h3 className="mb-1 text-sm font-semibold text-white">{report.title}</h3>
      <p className="mb-4 flex-1 text-xs text-slate-400">{report.description}</p>
      <span className="text-xs font-medium text-brand-400 transition group-hover:text-brand-300">
        View &rarr;
      </span>
    </Link>
  );
}

function ExportRow({
  item,
  busy,
  disabled,
  disabledReason,
  onDownload,
}: {
  item: ExportItem;
  busy: boolean;
  disabled: boolean;
  disabledReason?: string;
  onDownload: () => void;
}) {
  const Icon = item.icon;
  return (
    <tr className={clsx("transition hover:bg-slate-800/30", disabledReason && "opacity-60")}>
      <td className="px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
            <Icon size={14} />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-200">{item.name}</p>
            <p className="mt-0.5 text-xs text-slate-500 md:hidden">
              {item.description}
            </p>
            {disabledReason && (
              <p className="mt-0.5 text-[11px] text-amber-400/80">{disabledReason}</p>
            )}
          </div>
        </div>
      </td>
      <td className="hidden px-5 py-4 text-xs text-slate-400 md:table-cell">
        {item.description}
      </td>
      <td className="px-5 py-4 text-right">
        <button
          type="button"
          onClick={onDownload}
          disabled={busy || disabled}
          title={disabledReason}
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition",
            "border-slate-700 bg-slate-800 text-slate-200 hover:border-brand-500 hover:bg-brand-600/10 hover:text-white",
            "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-slate-700 disabled:hover:bg-slate-800 disabled:hover:text-slate-200",
          )}
        >
          {busy ? (
            <>
              <Loader2 size={12} className="animate-spin" />
              Downloading…
            </>
          ) : (
            <>
              <Download size={12} />
              Download CSV
            </>
          )}
        </button>
      </td>
    </tr>
  );
}

function Banner({
  state,
  onDismiss,
}: {
  state: BannerState;
  onDismiss: () => void;
}) {
  const success = state.kind === "success";
  return (
    <div
      role={success ? "status" : "alert"}
      className={clsx(
        "mb-3 flex items-start justify-between gap-3 rounded-xl border p-3 text-xs",
        success
          ? "border-green-900 bg-green-950/50 text-green-300"
          : "border-red-900 bg-red-950/60 text-red-300",
      )}
    >
      <div className="flex items-start gap-2">
        {success ? (
          <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0 text-green-400" />
        ) : (
          <AlertCircle size={14} className="mt-0.5 flex-shrink-0 text-red-400" />
        )}
        <span>{state.message}</span>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-xs font-medium opacity-70 transition hover:opacity-100"
      >
        Dismiss
      </button>
    </div>
  );
}
