"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Search,
  Lightbulb,
  BarChart2,
  MessageSquare,
  Settings,
  Zap,
} from "lucide-react";

const navItems = [
  { label: "Overview", href: "overview", icon: LayoutDashboard },
  { label: "Search", href: "search", icon: Search },
  { label: "Insights", href: "insights", icon: Lightbulb },
  { label: "Reports", href: "reports", icon: BarChart2 },
];

export function Sidebar({ propertyId }: { propertyId: number }) {
  const pathname = usePathname();
  const base = `/properties/${propertyId}`;

  return (
    <aside className="flex h-full w-56 flex-col border-r border-slate-800 bg-slate-950">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-800 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-black text-white">
          P
        </div>
        <span className="text-sm font-bold tracking-tight text-white">PRISM</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-3">
        <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-slate-600">
          Analytics
        </p>
        {navItems.map(({ label, href, icon: Icon }) => {
          const path = `${base}/${href}`;
          const active = pathname.startsWith(path);
          return (
            <Link
              key={href}
              href={path}
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
            AI
          </p>
          <Link
            href="/chat"
            className={clsx(
              "mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
              pathname === "/chat"
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:bg-slate-900 hover:text-white",
            )}
          >
            <MessageSquare size={16} />
            Chat
          </Link>
        </div>
      </nav>

      {/* Bottom */}
      <div className="border-t border-slate-800 p-3">
        <Link
          href="/settings/integrations"
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:text-white transition"
        >
          <Settings size={16} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
