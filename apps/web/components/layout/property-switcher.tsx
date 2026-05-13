"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChevronDown, Plus } from "lucide-react";
import { clsx } from "clsx";
import { useProperties } from "@/hooks/use-properties";
import type { PropertyResponse } from "@/lib/api-client";
import { isGA4Linked, isGSCLinked } from "@/lib/property-features";
import { NewPropertyModal } from "./new-property-modal";

interface PropertySwitcherProps {
  currentPropertyId: number;
}

const KNOWN_SECTIONS = ["overview", "search", "insights", "reports"] as const;
type Section = (typeof KNOWN_SECTIONS)[number];

function detectSection(pathname: string): Section {
  // pathname looks like /properties/4/overview or /properties/4/search/...
  const match = pathname.match(/^\/properties\/\d+\/([^/?#]+)/);
  if (match) {
    const seg = match[1] as Section;
    if ((KNOWN_SECTIONS as readonly string[]).includes(seg)) return seg;
  }
  return "overview";
}

export function PropertySwitcher({ currentPropertyId }: PropertySwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: properties, isLoading } = useProperties();
  const [open, setOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const current = useMemo(() => {
    if (!properties) return null;
    return properties.find((p) => p.id === currentPropertyId) ?? null;
  }, [properties, currentPropertyId]);

  function handleSelect(p: PropertyResponse) {
    setOpen(false);
    if (p.id === currentPropertyId) return;
    const section = detectSection(pathname ?? "");
    router.push(`/properties/${p.id}/${section}`);
  }

  function openNew() {
    setOpen(false);
    setModalOpen(true);
  }

  return (
    <>
      <div className="relative" ref={containerRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-left transition hover:border-slate-700 hover:bg-slate-800"
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              {current?.display_name ?? (isLoading ? "Loading…" : "Select property")}
            </p>
            {current && (
              <div className="mt-1 flex items-center gap-1">
                <IntegrationPill linked={isGA4Linked(current)} label="GA4" />
                <IntegrationPill linked={isGSCLinked(current)} label="GSC" />
              </div>
            )}
          </div>
          <ChevronDown
            size={14}
            className={clsx(
              "flex-shrink-0 text-slate-500 transition",
              open && "rotate-180",
            )}
          />
        </button>

        {open && (
          <div
            role="listbox"
            className="absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 shadow-2xl"
          >
            {properties && properties.length > 0 ? (
              properties.map((p) => {
                const isCurrent = p.id === currentPropertyId;
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="option"
                    aria-selected={isCurrent}
                    onClick={() => handleSelect(p)}
                    className={clsx(
                      "flex w-full items-start justify-between gap-2 px-3 py-2 text-left transition",
                      isCurrent
                        ? "bg-slate-800 text-white"
                        : "text-slate-300 hover:bg-slate-800/60 hover:text-white",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{p.display_name}</p>
                      <div className="mt-1 flex items-center gap-1">
                        <IntegrationPill linked={isGA4Linked(p)} label="GA4" />
                        <IntegrationPill linked={isGSCLinked(p)} label="GSC" />
                      </div>
                    </div>
                    {isCurrent && (
                      <span className="mt-1 text-xs text-brand-400">current</span>
                    )}
                  </button>
                );
              })
            ) : (
              <p className="px-3 py-3 text-xs text-slate-500">
                {isLoading ? "Loading properties…" : "No properties yet."}
              </p>
            )}

            <div className="border-t border-slate-800">
              <button
                type="button"
                onClick={openNew}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-brand-400 transition hover:bg-slate-800/60 hover:text-brand-300"
              >
                <Plus size={14} />
                Add new property
              </button>
            </div>
          </div>
        )}
      </div>

      <NewPropertyModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}

function IntegrationPill({ linked, label }: { linked: boolean; label: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider",
        linked
          ? "bg-green-500/15 text-green-400"
          : "bg-slate-800 text-slate-500",
      )}
      title={linked ? `${label} linked` : `${label} not linked`}
    >
      {label}
    </span>
  );
}
