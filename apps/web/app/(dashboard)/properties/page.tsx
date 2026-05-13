"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { CheckCircle2, ExternalLink, Loader2, Plus, XCircle } from "lucide-react";
import { useProperties } from "@/hooks/use-properties";
import { propertiesApi, propertiesApiExt, type PropertyResponse } from "@/lib/api-client";
import { isGA4Linked, isGSCLinked } from "@/lib/property-features";
import { NewPropertyModal } from "@/components/layout/new-property-modal";

export default function PropertiesIndexPage() {
  const router = useRouter();
  const { data: properties, isLoading, isError, error } = useProperties();
  const [modalOpen, setModalOpen] = useState(false);

  // Empty state: redirect to onboarding (extremely rare).
  useEffect(() => {
    if (!isLoading && properties && properties.length === 0) {
      router.replace("/onboarding");
    }
  }, [isLoading, properties, router]);

  return (
    <div className="min-h-screen bg-slate-950 px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white">Your properties</h1>
            <p className="mt-1 text-sm text-slate-400">
              Each property is one website or app you track in PRISM.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            <Plus size={14} />
            Add new property
          </button>
        </div>

        {isLoading && <CardsSkeleton />}

        {isError && (
          <div className="rounded-xl border border-red-900 bg-red-950/60 p-4 text-sm text-red-300">
            Failed to load properties: {(error as Error).message}
          </div>
        )}

        {properties && properties.length > 0 && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {properties.map((p) => (
              <PropertyCard key={p.id} property={p} />
            ))}
          </div>
        )}
      </div>

      <NewPropertyModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}

function PropertyCard({ property }: { property: PropertyResponse }) {
  const ga4 = isGA4Linked(property);
  const gsc = isGSCLinked(property);
  const created = new Date(property.created_at);
  const createdLabel = isNaN(created.getTime())
    ? property.created_at
    : created.toLocaleDateString();

  return (
    <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4">
        <h2 className="truncate text-base font-semibold text-white">
          {property.display_name}
        </h2>
        <p className="mt-0.5 text-xs text-slate-500">
          {property.timezone} · created {createdLabel}
        </p>
      </div>

      <div className="mb-5 space-y-3">
        <IntegrationRow
          label="GA4"
          linked={ga4}
          propertyId={property.id}
          kind="ga4"
        />
        <IntegrationRow
          label="Search Console"
          linked={gsc}
          propertyId={property.id}
          kind="gsc"
        />
      </div>

      <div className="mt-auto flex items-center justify-between gap-2">
        <Link
          href={`/properties/${property.id}/overview` as Route}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700"
        >
          Open dashboard
          <ExternalLink size={12} />
        </Link>
      </div>
    </div>
  );
}

function IntegrationRow({
  label,
  linked,
  propertyId,
  kind,
}: {
  label: string;
  linked: boolean;
  propertyId: number;
  kind: "ga4" | "gsc";
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const linkMutation = useMutation({
    mutationFn: async (raw: string) => {
      if (kind === "ga4") return propertiesApi.linkGA4(propertyId, raw.trim());
      return propertiesApiExt.linkGSC(propertyId, raw.trim());
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["properties"] });
      queryClient.invalidateQueries({ queryKey: ["property", propertyId] });
      setEditing(false);
      setValue("");
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          {linked ? (
            <CheckCircle2 size={14} className="text-green-400" />
          ) : (
            <XCircle size={14} className="text-slate-600" />
          )}
          <span
            className={clsx(
              "font-medium",
              linked ? "text-slate-300" : "text-slate-500",
            )}
          >
            {label} {linked ? "linked" : "not linked"}
          </span>
        </div>
        {!linked && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-md border border-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-300 transition hover:border-brand-500 hover:text-white"
          >
            Connect
          </button>
        )}
      </div>

      {editing && !linked && (
        <div className="mt-2 space-y-1.5">
          <input
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              kind === "ga4"
                ? "properties/123456789"
                : "sc-domain:augmex.io  or  https://augmex.io/"
            }
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-[11px] text-white placeholder-slate-600 focus:border-brand-500 focus:outline-none"
          />
          <p className="text-[10px] text-slate-500">
            {kind === "ga4"
              ? "GA4 → Admin → Property → Property details"
              : "Use sc-domain: prefix for domain properties, or full URL for URL-prefix"}
          </p>
          {error && (
            <p className="text-[11px] text-red-400">{error}</p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => linkMutation.mutate(value)}
              disabled={!value.trim() || linkMutation.isPending}
              className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
            >
              {linkMutation.isPending && <Loader2 size={11} className="animate-spin" />}
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setValue("");
                setError(null);
              }}
              className="rounded-md border border-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-400 transition hover:text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CardsSkeleton() {
  return (
    <div className="grid animate-pulse grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-44 rounded-xl border border-slate-800 bg-slate-900" />
      ))}
    </div>
  );
}
