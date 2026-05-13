import type { PropertyResponse } from "@/lib/api-client";

export function isGA4Linked(p: PropertyResponse): boolean {
  return !!p.ga4_property_id;
}

export function isGSCLinked(p: PropertyResponse): boolean {
  return !!p.gsc_site_url;
}

export function isClarityLinked(p: PropertyResponse): boolean {
  return !!p.clarity_project_id;
}

// ── Microsoft Clarity deep-link builders ─────────────────────────────────────
//
// Clarity URL format (as of 2025): /projects/view/{project_id}/{section}?Page={url}
// The Page filter accepts a URL-encoded path or full URL. If the property's
// landing pages are stored as relative paths (most common), Clarity will still
// open at the project dashboard with the filter applied — even if zero matches
// the user can clear the filter to browse.

const _CLARITY_BASE = "https://clarity.microsoft.com/projects/view";

export function clarityDashboardUrl(projectId: string): string {
  return `${_CLARITY_BASE}/${projectId}/dashboard`;
}

export function clarityHeatmapUrl(projectId: string, page: string): string {
  return `${_CLARITY_BASE}/${projectId}/heatmaps?Page=${encodeURIComponent(page)}`;
}

export function clarityRecordingsUrl(projectId: string, page: string): string {
  return `${_CLARITY_BASE}/${projectId}/recordings?Page=${encodeURIComponent(page)}`;
}

export function hasEcommerceData(kpis: { total_revenue?: { value: number } | number }): boolean {
  if (kpis == null) return false;
  const raw = (kpis as { total_revenue?: { value: number } | number }).total_revenue;
  if (raw == null) return false;
  if (typeof raw === "number") return raw > 0;
  return (raw.value ?? 0) > 0;
}
