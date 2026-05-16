"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname, useSearchParams } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Search,
  Lightbulb,
  BarChart2,
  MessageSquare,
  Settings,
  Newspaper,
  Pin,
  Table2,
  FileText,
  Activity,
  ExternalLink,
  Gauge,
  Zap,
} from "lucide-react";
import { PropertySwitcher } from "./property-switcher";
import { useProperty } from "@/hooks/use-properties";
import {
  clarityDashboardUrl,
  isClarityLinked,
} from "@/lib/property-features";

const analyticsNavItems = [
  { label: "Overview", href: "overview", icon: LayoutDashboard },
  { label: "Pages", href: "pages", icon: FileText },
  { label: "Performance", href: "performance", icon: Gauge },
  { label: "Search", href: "search", icon: Search },
  { label: "Insights", href: "insights", icon: Lightbulb },
  { label: "Reports", href: "reports", icon: BarChart2 },
];

// Query-param routes: active when pathname prefix matches AND property_id matches
const queryNavItems = [
  { label: "Brief",   icon: Newspaper,     prefix: null,       href: (id: number) => `/properties/${id}/brief` },
  { label: "Chat",    icon: MessageSquare, prefix: "/chat",    href: (id: number) => `/chat?property_id=${id}` },
  { label: "Pinned",  icon: Pin,           prefix: "/pinned",  href: (id: number) => `/pinned?property_id=${id}` },
  { label: "Explore", icon: Table2,        prefix: "/explore", href: (id: number) => `/explore?property_id=${id}` },
  { label: "Actions", icon: Zap,           prefix: "/actions", href: (id: number) => `/actions?property_id=${id}` },
];

export function Sidebar({ propertyId }: { propertyId: number }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const base = `/properties/${propertyId}`;
  const { data: property } = useProperty(propertyId);
  const clarityProjectId =
    property && isClarityLinked(property) ? property.clarity_project_id! : null;

  // property_id from query string — used for active state on query-param routes
  const qpPropertyId = searchParams.get("property_id");
  const isCurrentProperty = qpPropertyId === String(propertyId);

  return (
    <aside className="flex h-full w-56 flex-col border-r border-slate-800 bg-slate-950">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-800 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-black text-white">
          P
        </div>
        <span className="text-sm font-bold tracking-tight text-white">PRISM</span>
      </div>

      {/* Property switcher */}
      <div className="border-b border-slate-800 p-3">
        <PropertySwitcher currentPropertyId={propertyId} />
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-3">
        <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-slate-600">
          Analytics
        </p>
        {analyticsNavItems.map(({ label, href, icon: Icon }) => {
          const path = `${base}/${href}`;
          const active = pathname.startsWith(path);
          return (
            <Link
              key={href}
              href={path as Route}
              className={clsx(
                "mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-white",
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}

        <div className="mt-4 border-t border-slate-800 pt-4">
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-slate-600">
            AI Analyst
          </p>
          {queryNavItems.map(({ label, icon: Icon, prefix, href }) => {
            // Brief is a path-based route; the rest match on prefix + property_id param
            const active = prefix === null
              ? pathname.startsWith(`${base}/brief`)
              : pathname.startsWith(prefix) && isCurrentProperty;
            return (
              <Link
                key={label}
                href={href(propertyId) as Route}
                className={clsx(
                  "mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
                  active
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:bg-slate-900 hover:text-white",
                )}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Bottom */}
      <div className="border-t border-slate-800 p-3">
        {clarityProjectId && (
          <a
            href={clarityDashboardUrl(clarityProjectId)}
            target="_blank"
            rel="noopener noreferrer"
            className="mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:text-white transition"
            title="Open Microsoft Clarity"
          >
            <Activity size={16} />
            Clarity
            <ExternalLink size={11} className="ml-auto opacity-60" />
          </a>
        )}
        <Link
          href={`/properties/${propertyId}/settings` as Route}
          className={clsx(
            "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
            pathname.startsWith(`/properties/${propertyId}/settings`)
              ? "bg-slate-800 text-white"
              : "text-slate-500 hover:text-white",
          )}
        >
          <Settings size={16} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
