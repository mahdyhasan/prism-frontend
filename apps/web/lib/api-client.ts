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
    throw new Error(`API ${res.status}: ${message}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
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

export interface OverviewKPIs {
  sessions: KPIValue;
  users: KPIValue;
  new_users: KPIValue;
  engagement_rate: KPIValue;
  bounce_rate: KPIValue;
  conversions: KPIValue;
  total_revenue: KPIValue;
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
  bounce_rate: number;
}

export interface TrafficSourceRow {
  source: string;
  medium: string;
  sessions: number;
  users: number;
  conversions: number;
}

export interface DeviceRow {
  device_category: string;
  sessions: number;
  users: number;
  conversions: number;
}

export const authApi = {
  sync: (payload: {
    google_id_token: string;
    google_refresh_token: string;
    name: string;
    email: string;
    google_sub: string;
  }) => api.post<AuthSyncResponse>("/api/v1/auth/sync", payload),

  me: () => api.get<{ id: number; email: string; name: string; role: string }>("/api/v1/auth/me"),
};

export const propertiesApi = {
  list: () => api.get<PropertyResponse[]>("/api/v1/properties"),
  create: (body: { display_name: string; timezone?: string; currency?: string }) =>
    api.post<PropertyResponse>("/api/v1/properties", body),
  linkGA4: (id: number, ga4PropertyId: string) =>
    api.post<PropertyResponse>(`/api/v1/properties/${id}/link-ga4`, {
      ga4_property_id: ga4PropertyId,
    }),
  triggerSync: (id: number, source = "ga4") =>
    api.post(`/api/v1/properties/${id}/sync`, { source }),
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
