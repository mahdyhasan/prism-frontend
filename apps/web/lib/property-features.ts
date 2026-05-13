import type { PropertyResponse } from "@/lib/api-client";

export function isGA4Linked(p: PropertyResponse): boolean {
  return !!p.ga4_property_id;
}

export function isGSCLinked(p: PropertyResponse): boolean {
  return !!p.gsc_site_url;
}

export function hasEcommerceData(kpis: { total_revenue?: { value: number } | number }): boolean {
  if (kpis == null) return false;
  const raw = (kpis as { total_revenue?: { value: number } | number }).total_revenue;
  if (raw == null) return false;
  if (typeof raw === "number") return raw > 0;
  return (raw.value ?? 0) > 0;
}
