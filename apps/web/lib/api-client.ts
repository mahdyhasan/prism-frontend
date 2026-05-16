const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "prism_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class APIError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "APIError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    const message = body?.error ?? res.statusText;
    throw new APIError(res.status, message);
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ── Typed API calls ───────────────────────────────────────────────────────────

export interface AuthSyncResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  tenant_id: number;
  name: string;
  email: string;
  role: string;
  has_google_linked: boolean;
  property_id: number | null;
}

export interface GoogleRegisterPayload {
  google_id_token: string;
  google_refresh_token: string;
  google_sub: string;
  email: string;
  name: string;
  ga4_property_id: string;
  gsc_site_url?: string;
  display_name?: string;
  timezone?: string;
  currency?: string;
}

export interface GA4PropertyOption {
  property_id: string;
  display_name: string;
  account_name: string;
}

export interface GSCSiteOption {
  site_url: string;
  permission_level: string;
}

export interface GoogleDiscoverResponse {
  ga4_properties: GA4PropertyOption[];
  gsc_sites: GSCSiteOption[];
}

export interface SyncJobResponse {
  id: number;
  property_id: number;
  source: string;
  kind: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  rows_pulled: number;
  error: string | null;
  created_at: string;
}

export interface IntegrationSyncStatus {
  source: string;
  status: string | null;
  last_finished_at: string | null;
  error: string | null;
  job_id: number | null;
  rows_pulled: number | null;
}

export interface PropertySyncStatusResponse {
  ga4: IntegrationSyncStatus;
  gsc: IntegrationSyncStatus;
}

export interface LLMConfigResponse {
  property_id: number;
  llm_provider: string;
  llm_model: string;
  has_api_key_override: boolean;
}

export interface PropertyResponse {
  id: number;
  tenant_id: number;
  display_name: string;
  ga4_property_id: string | null;
  gsc_site_url: string | null;
  timezone: string;
  currency: string;
  status: string;
  created_at: string;
  primary_conversion_events?: string[] | null;
  clarity_project_id?: string | null;
  has_clarity_api_token?: boolean;
}

export interface AvailableEvent {
  event_name: string;
  total_count: number;
  is_ga4_conversion: boolean;
}

export interface OverviewResponse {
  start_date: string;
  end_date: string;
  compare_start_date: string | null;
  compare_end_date: string | null;
  kpis: OverviewKPIs;
  sessions_trend: DailyPoint[];
  top_landing_pages: LandingPageRow[];
  top_traffic_sources: TrafficSourceRow[];
  devices: DeviceRow[];
  last_synced_at: string | null;
}

export interface KPIValue {
  value: number;
  previous_value: number | null;
  delta_percent: number | null;
}

export interface PrimaryEventConversion {
  event_name: string;
  count: number;
  rate_per_session: number;
  delta_count_percent: number | null;
  delta_rate_percent: number | null;
}

export interface OverviewKPIs {
  sessions: KPIValue;
  users: KPIValue;
  new_users: KPIValue;
  engagement_rate: KPIValue;
  bounce_rate: KPIValue;
  conversions: KPIValue;
  total_revenue: KPIValue;
  primary_event_conversions: PrimaryEventConversion[];
}

export interface DailyPoint {
  date: string;
  sessions: number;
  users: number;
}

export interface LandingPageRow {
  landing_page: string;
  sessions: number;
  users: number;
  conversions: number;
  conversion_rate: number | null;
  bounce_rate: number;
}

export interface TrafficSourceRow {
  source: string;
  medium: string;
  sessions: number;
  users: number;
  conversions: number;
  conversion_rate: number | null;
}

export interface DeviceRow {
  device_category: string;
  sessions: number;
  users: number;
  conversions: number;
  conversion_rate: number | null;
}

export const authApi = {
  sync: (payload: {
    google_id_token: string;
    google_refresh_token: string;
    name: string;
    email: string;
    google_sub: string;
  }) => api.post<AuthSyncResponse>("/api/v1/auth/sync", payload),

  login: (email: string, password: string) =>
    api.post<AuthSyncResponse>("/api/v1/auth/login", { email, password }),

  signup: (email: string, name: string, password: string) =>
    api.post<AuthSyncResponse>("/api/v1/auth/signup", { email, name, password }),

  linkGoogle: (google_id_token: string, google_refresh_token: string) =>
    api.post<AuthSyncResponse>("/api/v1/auth/link-google", {
      google_id_token,
      google_refresh_token,
    }),

  registerGoogle: (payload: GoogleRegisterPayload) =>
    api.post<AuthSyncResponse>("/api/v1/auth/register-google", payload),

  discover: (payload: {
    google_id_token: string;
    google_access_token?: string;
    google_refresh_token?: string;
  }) =>
    api.post<GoogleDiscoverResponse>("/api/v1/auth/google/discover", payload),

  discoverMine: () =>
    api.get<GoogleDiscoverResponse>("/api/v1/auth/google/discover-mine"),

  me: () =>
    api.get<{ id: number; email: string; name: string; role: string; has_google_linked: boolean }>(
      "/api/v1/auth/me",
    ),
};

export const propertiesApi = {
  list: () => api.get<PropertyResponse[]>("/api/v1/properties"),
  get: (id: number) => api.get<PropertyResponse>(`/api/v1/properties/${id}`),
  create: (body: { display_name: string; timezone?: string; currency?: string }) =>
    api.post<PropertyResponse>("/api/v1/properties", body),
  linkGA4: (id: number, ga4PropertyId: string) =>
    api.post<PropertyResponse>(`/api/v1/properties/${id}/link-ga4`, {
      ga4_property_id: ga4PropertyId,
    }),
  unlinkGA4: (id: number) => api.delete<PropertyResponse>(`/api/v1/properties/${id}/ga4`),
  linkGSC: (id: number, siteUrl: string) =>
    api.post<PropertyResponse>(`/api/v1/properties/${id}/link-gsc`, {
      site_url: siteUrl,
    }),
  unlinkGSC: (id: number) => api.delete<PropertyResponse>(`/api/v1/properties/${id}/gsc`),
  triggerSync: (id: number, source: "ga4" | "gsc" = "ga4") =>
    api.post<SyncJobResponse>(`/api/v1/properties/${id}/sync`, { source }),
  getSyncStatus: (id: number) =>
    api.get<PropertySyncStatusResponse>(`/api/v1/properties/${id}/sync-status`),
  getLLMConfig: (id: number) =>
    api.get<LLMConfigResponse>(`/api/v1/properties/${id}/llm-config`),
  updateLLMConfig: (
    id: number,
    body: { llm_provider: string; llm_model: string; llm_api_key?: string },
  ) => api.put<LLMConfigResponse>(`/api/v1/properties/${id}/llm-config`, body),

  getAvailableEvents: (id: number) =>
    api.get<AvailableEvent[]>(`/api/v1/properties/${id}/available-events`),

  setPrimaryConversionEvents: (id: number, event_names: string[]) =>
    api.put<PropertyResponse>(`/api/v1/properties/${id}/primary-conversion-events`, {
      event_names,
    }),

  setClarityProjectId: (id: number, clarity_project_id: string | null) =>
    api.put<PropertyResponse>(`/api/v1/properties/${id}/clarity-project-id`, {
      clarity_project_id,
    }),

  setClarityApiToken: (id: number, api_token: string | null) =>
    api.put<PropertyResponse>(`/api/v1/properties/${id}/clarity-api-token`, {
      api_token,
    }),
};

export const syncApi = {
  getJob: (jobId: number) => api.get<SyncJobResponse>(`/api/v1/sync/jobs/${jobId}`),
  listJobs: (propertyId?: number) =>
    api.get<SyncJobResponse[]>(
      propertyId ? `/api/v1/sync/jobs?property_id=${propertyId}` : "/api/v1/sync/jobs",
    ),
};

export const overviewApi = {
  get: (
    propertyId: number,
    params: {
      preset?: string;
      start_date?: string;
      end_date?: string;
      compare_to?: string;
    },
  ) => {
    const qs = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params).filter(([, v]) => v != null) as [string, string][],
      ),
    ).toString();
    return api.get<OverviewResponse>(`/api/v1/properties/${propertyId}/overview?${qs}`);
  },
};

// ── Search Console (GSC) ──────────────────────────────────────────────────────

export interface SearchKPIs {
  clicks: number;
  impressions: number;
  ctr: number;
  avg_position: number;
  clicks_delta: number | null;
  impressions_delta: number | null;
  ctr_delta: number | null;
  position_delta: number | null;
}

export interface SearchDailyPoint {
  date: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface SearchOverviewResponse {
  kpis: SearchKPIs;
  daily_trend: SearchDailyPoint[];
}

export interface SearchQuery {
  query: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface SearchPage {
  page: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface SearchOpportunity {
  query: string;
  page: string;
  position: number;
  impressions: number;
  clicks: number;
  ctr: number;
}

interface SearchRangeParams {
  start: string;
  end: string;
  compare_start?: string;
  compare_end?: string;
}

function buildQS(params: object): string {
  return new URLSearchParams(
    Object.fromEntries(
      Object.entries(params).filter(([, v]) => v != null) as [string, string][],
    ),
  ).toString();
}

// ── AI Insights ───────────────────────────────────────────────────────────────

export type InsightKind =
  | "anomaly"
  | "trend"
  | "opportunity"
  | "decay"
  | "cannibalization";

export type InsightSeverity = "low" | "medium" | "high" | "critical";

export type InsightStatus = "new" | "acknowledged" | "dismissed";

export interface InsightResponse {
  id: number;
  property_id: number;
  kind: InsightKind;
  severity: InsightSeverity;
  title: string;
  summary: string;
  supporting_data: Record<string, unknown>;
  detected_at: string;
  period_start: string;
  period_end: string;
  status: InsightStatus;
  claude_model_used: string | null;
  claude_input_tokens: number | null;
  claude_output_tokens: number | null;
  created_at: string;
  updated_at: string;
}

export interface InsightsListResponse {
  items: InsightResponse[];
}

export interface InsightsGenerateResponse {
  generated: number;
  total_anomalies_detected: number;
}

export const insightsApi = {
  list: (propertyId: number, params: { status?: InsightStatus } = {}) => {
    const qs = buildQS(params);
    const suffix = qs ? `?${qs}` : "";
    return api.get<InsightsListResponse>(
      `/api/v1/properties/${propertyId}/insights${suffix}`,
    );
  },
  updateStatus: (
    propertyId: number,
    insightId: number,
    status: Exclude<InsightStatus, "new">,
  ) =>
    api.patch<InsightResponse>(
      `/api/v1/properties/${propertyId}/insights/${insightId}`,
      { status },
    ),
  generate: (propertyId: number) =>
    api.post<InsightsGenerateResponse>(
      `/api/v1/properties/${propertyId}/insights/generate`,
      {},
    ),
};

export const searchApi = {
  getOverview: (propertyId: number, params: SearchRangeParams) => {
    const qs = buildQS(params);
    return api.get<SearchOverviewResponse>(
      `/api/v1/properties/${propertyId}/search/overview?${qs}`,
    );
  },
  getQueries: (
    propertyId: number,
    params: { start: string; end: string; limit?: number },
  ) => {
    const qs = buildQS(params);
    return api.get<SearchQuery[]>(`/api/v1/properties/${propertyId}/search/queries?${qs}`);
  },
  getPages: (
    propertyId: number,
    params: { start: string; end: string; limit?: number },
  ) => {
    const qs = buildQS(params);
    return api.get<SearchPage[]>(`/api/v1/properties/${propertyId}/search/pages?${qs}`);
  },
  getOpportunities: (
    propertyId: number,
    params: { start: string; end: string },
  ) => {
    const qs = buildQS(params);
    return api.get<SearchOpportunity[]>(
      `/api/v1/properties/${propertyId}/search/opportunities?${qs}`,
    );
  },
};

// ── Exports (CSV) ─────────────────────────────────────────────────────────────
//
// These helpers return relative API paths only. The actual download is
// performed by the Reports page via an authenticated fetch + Blob URL,
// since CSV downloads can't piggy-back on a normal anchor click without
// putting the JWT in the URL.

export type ExportKind =
  | "ga4_sessions"
  | "ga4_pages"
  | "ga4_sources"
  | "ga4_devices"
  | "ga4_geo"
  | "gsc_queries"
  | "gsc_pages";

const exportPathMap: Record<ExportKind, string> = {
  ga4_sessions: "ga4/sessions.csv",
  ga4_pages: "ga4/pages.csv",
  ga4_sources: "ga4/sources.csv",
  ga4_devices: "ga4/devices.csv",
  ga4_geo: "ga4/geo.csv",
  gsc_queries: "gsc/queries.csv",
  gsc_pages: "gsc/pages.csv",
};

export const exportsApi = {
  apiBase: API_BASE,
  tokenKey: TOKEN_KEY,
  path: (
    propertyId: number,
    kind: ExportKind,
    params: { start: string; end: string },
  ): string => {
    const qs = buildQS(params);
    return `/api/v1/properties/${propertyId}/exports/${exportPathMap[kind]}?${qs}`;
  },
};

// ── Tier 1 widget types & extensions ──────────────────────────────────────────

export interface ChannelBreakdownItem {
  channel_group: string;
  sessions: number;
  users: number;
  conversions: number;
  conversion_rate: number | null;
  revenue: number;
  /** 0..1 share of total sessions */
  share: number;
}

export interface HourlyHeatmapPoint {
  /** 0 = Sunday, 6 = Saturday */
  day_of_week: number;
  /** 0..23 */
  hour: number;
  sessions: number;
  users: number;
}

export interface UserTypeStats {
  sessions: number;
  users: number;
  engaged_sessions: number;
}

export interface UserTypeSplit {
  new: UserTypeStats | null;
  returning: UserTypeStats | null;
  total: UserTypeStats;
}

export interface AppearanceBreakdownItem {
  search_appearance: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export type SearchType = "web" | "image" | "video" | "news" | "googleNews" | "discover";

export interface SearchTypeBreakdownItem {
  search_type: SearchType;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

interface DateRangeParams {
  start: string;
  end: string;
}

// ── Page Performance (Phase B) ────────────────────────────────────────────────

export interface PageRow {
  page: string;
  sessions: number;
  users: number;
  engaged_sessions: number;
  conversions: number;
  revenue: number;
  bounce_rate: number;
  engagement_rate: number | null;
  conversion_rate: number | null;
  avg_session_duration: number;
  exits: number;
  exit_rate: number | null;
  clicks: number;
  impressions: number;
  ctr: number;
  avg_position: number;
  // Microsoft Clarity (null when no data available yet)
  frustration_score: number | null;
  scroll_depth_avg: number | null;
  health_score: number | null;
}

export type DeviceCategory = "mobile" | "desktop" | "tablet";

export interface PagePerformanceResponse {
  start_date: string;
  end_date: string;
  rows: PageRow[];
  total_rows: number;
  device: DeviceCategory | null;
}

export type PageSortKey =
  | "sessions"
  | "conv_rate"
  | "engagement_rate"
  | "bounce_rate"
  | "avg_duration"
  | "exit_rate"
  | "clicks"
  | "impressions"
  | "position"
  | "health_score"
  | "frustration_score"
  | "scroll_depth";

export const pagesApi = {
  list: (
    propertyId: number,
    params: {
      start?: string;
      end?: string;
      min_sessions?: number;
      sort_by?: PageSortKey;
      sort_desc?: boolean;
      limit?: number;
      device?: DeviceCategory;
    } = {},
  ) => {
    const qs = buildQS(params);
    const suffix = qs ? `?${qs}` : "";
    return api.get<PagePerformanceResponse>(
      `/api/v1/properties/${propertyId}/pages${suffix}`,
    );
  },
};

export const overviewWidgetsApi = {
  getChannels: (propertyId: number, params: DateRangeParams) => {
    const qs = buildQS(params);
    return api.get<ChannelBreakdownItem[]>(
      `/api/v1/properties/${propertyId}/overview/channels?${qs}`,
    );
  },
  getHourly: (propertyId: number, params: DateRangeParams) => {
    const qs = buildQS(params);
    return api.get<HourlyHeatmapPoint[]>(
      `/api/v1/properties/${propertyId}/overview/hourly?${qs}`,
    );
  },
  getUserType: (propertyId: number, params: DateRangeParams) => {
    const qs = buildQS(params);
    return api.get<UserTypeSplit>(
      `/api/v1/properties/${propertyId}/overview/user-type?${qs}`,
    );
  },
};

export const searchWidgetsApi = {
  getAppearance: (propertyId: number, params: DateRangeParams) => {
    const qs = buildQS(params);
    return api.get<AppearanceBreakdownItem[]>(
      `/api/v1/properties/${propertyId}/search/appearance?${qs}`,
    );
  },
  getSearchTypes: (propertyId: number, params: DateRangeParams) => {
    const qs = buildQS(params);
    return api.get<SearchTypeBreakdownItem[]>(
      `/api/v1/properties/${propertyId}/search/types?${qs}`,
    );
  },
};

// ── Properties API extensions (append-only) ───────────────────────────────────
// Adds typed `get` and `linkGSC` helpers without mutating the existing
// `propertiesApi` declaration above (so parallel agents touching that block
// don't conflict).

export const propertiesApiExt = {
  get: (id: number) => api.get<PropertyResponse>(`/api/v1/properties/${id}`),
  linkGSC: (id: number, siteUrl: string) =>
    api.post<PropertyResponse>(`/api/v1/properties/${id}/link-gsc`, {
      site_url: siteUrl,
    }),
};

// ── Chat types ─────────────────────────────────────────────────────────────

export interface ChatSessionResponse {
  id: number;
  property_id: number;
  user_id: number;
  title: string | null;
  source_scope: string;
  created_at: string;
  last_message_at: string;
  messages?: ChatMessageResponse[];
}

export interface ChatMessageResponse {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  source_scope: string;
  created_at: string;
}

export interface PinnedQuestionResponse {
  id: number;
  property_id: number;
  title: string;
  prompt: string;
  source_scope: string;
  date_range_strategy: string;
  tags: string[] | null;
  created_at: string;
  updated_at: string;
  latest_run?: PinnedRunResponse | null;
}

export interface PinnedRunResponse {
  id: number;
  pin_id: number;
  run_at: string;
  answer_json: string | null;
  run_status: "pending" | "done" | "failed";
  error: string | null;
}

export interface DailyBriefResponse {
  id: number;
  property_id: number;
  brief_date: string;
  brief_json: string | null;
  generated_at: string;
  generation_count: number;
}

export interface BriefNotReadyResponse {
  status: "not_ready" | "error";
  brief: null;
  message: string;
}

export const chatApi = {
  createSession: (body: { property_id: number; source_scope?: string; title?: string }) =>
    api.post<ChatSessionResponse>("/api/v1/chat/sessions", body),

  listSessions: (property_id: number) =>
    api.get<ChatSessionResponse[]>(`/api/v1/chat/sessions?property_id=${property_id}`),

  getSession: (id: number) =>
    api.get<ChatSessionResponse>(`/api/v1/chat/sessions/${id}`),
};

export const pinnedApi = {
  list: (property_id: number) =>
    api.get<PinnedQuestionResponse[]>(`/api/v1/pinned?property_id=${property_id}`),

  create: (body: {
    property_id: number;
    title: string;
    prompt: string;
    source_scope?: string;
    date_range_strategy?: string;
    tags?: string[];
  }) => api.post<PinnedQuestionResponse>("/api/v1/pinned", body),

  get: (id: number) => api.get<PinnedQuestionResponse>(`/api/v1/pinned/${id}`),

  delete: (id: number) => api.delete<{ success: boolean }>(`/api/v1/pinned/${id}`),

  run: (id: number) =>
    api.post<{ status: string; run_id: number }>(`/api/v1/pinned/${id}/run`, {}),

  getRuns: (id: number) =>
    api.get<PinnedRunResponse[]>(`/api/v1/pinned/${id}/runs`),
};

export const briefApi = {
  get: (property_id: number) =>
    api.get<DailyBriefResponse | BriefNotReadyResponse>(
      `/api/v1/properties/${property_id}/brief`,
    ),

  regenerate: (property_id: number) =>
    api.post<{ status: string; message: string }>(
      `/api/v1/properties/${property_id}/brief/regenerate`,
      {},
    ),
};

// ── Actions ───────────────────────────────────────────────────────────────────

export type ActionStatus =
  | "pending_confirmation"
  | "confirmed"
  | "executing"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "expired";

export interface ActionResponse {
  id: number;
  property_id: number;
  tool_name: string;
  tool_input: Record<string, unknown>;
  status: ActionStatus;
  confirmation_required: boolean;
  created_at: string;
  confirmed_at: string | null;
  executed_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  /** Only present when status == "pending_confirmation" */
  confirmation_token: string | null;
}

export const actionsApi = {
  list: (propertyId: number, params: { status?: ActionStatus; limit?: number } = {}) => {
    const qs = buildQS({ property_id: propertyId, ...params });
    return api.get<ActionResponse[]>(`/api/v1/actions?${qs}`);
  },
  get: (id: number) => api.get<ActionResponse>(`/api/v1/actions/${id}`),
  confirm: (id: number, token: string) =>
    api.post<ActionResponse>(`/api/v1/actions/${id}/confirm`, { token }),
  cancel: (id: number) =>
    api.post<ActionResponse>(`/api/v1/actions/${id}/cancel`, {}),
};

// ── Core Web Vitals ───────────────────────────────────────────────────────────

export type CWVStatus = "good" | "needs_improvement" | "poor" | "unknown";

export interface PageCWVResponse {
  url: string;
  strategy: string;
  cwv_status: CWVStatus;
  lcp_ms: number | null;
  inp_ms: number | null;
  cls: number | null;
  fcp_ms: number | null;
  ttfb_ms: number | null;
  lighthouse_performance_score: number | null;
  audited_at: string | null;
  opportunities: unknown[];
}

export interface OriginCWVResponse {
  strategy: string;
  lcp_ms: number | null;
  inp_ms: number | null;
  cls: number | null;
  cwv_status: CWVStatus;
  audited_at: string | null;
}

export interface CWVProblemPage {
  url: string;
  strategy: string;
  cwv_status: CWVStatus;
  lcp_ms: number | null;
  inp_ms: number | null;
  cls: number | null;
  lighthouse_performance_score: number | null;
  audited_at: string | null;
}

export interface CWVScanResponse {
  pages: CWVProblemPage[];
  total: number;
}

export interface CWVMobileDesktopRow {
  url: string;
  mobile_status: CWVStatus;
  desktop_status: CWVStatus;
  mobile_lcp_ms: number | null;
  desktop_lcp_ms: number | null;
  lcp_gap_ms: number | null;
}

export interface CWVMobileDesktopResponse {
  rows: CWVMobileDesktopRow[];
}

export interface CWVTrendPoint {
  audited_at: string;
  cwv_status: CWVStatus;
  lcp_ms: number | null;
  inp_ms: number | null;
  cls: number | null;
  lighthouse_performance_score: number | null;
}

export interface CWVTrendResponse {
  url: string;
  strategy: string;
  trend: CWVTrendPoint[];
}

export const cwvApi = {
  getOrigin: (propertyId: number, strategy: "mobile" | "desktop" = "mobile") =>
    api.get<OriginCWVResponse>(
      `/api/v1/properties/${propertyId}/cwv/origin?strategy=${strategy}`,
    ),
  scanProblems: (
    propertyId: number,
    params: { strategy?: "mobile" | "desktop"; limit?: number } = {},
  ) => {
    const qs = buildQS(params);
    return api.get<CWVScanResponse>(
      `/api/v1/properties/${propertyId}/cwv/problems${qs ? `?${qs}` : ""}`,
    );
  },
  getMobileDesktop: (propertyId: number) =>
    api.get<CWVMobileDesktopResponse>(
      `/api/v1/properties/${propertyId}/cwv/mobile-desktop`,
    ),
};

// ── CWV + Actions settings ────────────────────────────────────────────────────

export interface PropertySettingsResponse {
  property_id: number;
  cwv_audit_enabled: boolean;
  cwv_top_pages_count: number;
  cwv_mobile_enabled: boolean;
  cwv_desktop_enabled: boolean;
  allow_destructive_actions: boolean;
}

export const propertySettingsApi = {
  get: (propertyId: number) =>
    api.get<PropertySettingsResponse>(`/api/v1/properties/${propertyId}/cwv/settings`),
  update: (propertyId: number, body: Partial<Omit<PropertySettingsResponse, "property_id">>) =>
    api.put<PropertySettingsResponse>(`/api/v1/properties/${propertyId}/cwv/settings`, body),
};

// SSE streaming helper for chat messages
export function streamChatMessage(
  sessionId: number,
  content: string,
  sourceScope: string,
  onEvent: (event: {
    type: "tool_start" | "tool_result" | "text_delta" | "done" | "error";
    [key: string]: unknown;
  }) => void,
): () => void {
  const token = getStoredToken();
  const controller = new AbortController();

  fetch(`${API_BASE}/api/v1/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, source_scope: sourceScope }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok || !res.body) {
      onEvent({ type: "error", message: `HTTP ${res.status}` });
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent(parsed);
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
    }
  }).catch((err: unknown) => {
    if (err instanceof Error && err.name !== "AbortError") {
      onEvent({ type: "error", message: String(err) });
    }
  });

  return () => controller.abort();
}
