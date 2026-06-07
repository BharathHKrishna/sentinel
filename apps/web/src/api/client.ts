import axios from 'axios'

const BASE_URL = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_BASE_URL ?? '/api'

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60_000,
})

// Request interceptor — add auth token if present
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('sentinel_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — unwrap error messages
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.message ??
      'An unexpected error occurred'
    return Promise.reject(new Error(message))
  }
)

export default apiClient

// ── Typed API helpers ──────────────────────────────────────────────────────────

export interface Region {
  id: number
  name: string
  geom: {
    type: 'Polygon'
    coordinates: number[][][]
  }
  detection_types: string[]
  cadence: number
  created_at: string
  owner_email: string | null
}

export interface SentinelEvent {
  id: number
  region_id: number
  detected_type: string
  confidence: number
  lat: number | null
  lon: number | null
  first_seen: string
  description: string | null
  before_tile_url: string | null
  after_tile_url: string | null
  created_at: string
  is_false_positive: boolean | null
}

export interface AlertSubscription {
  id: number
  region_id: number
  email: string | null
  slack_webhook: string | null
}

export interface RegionCreatePayload {
  name: string
  lat: number
  lon: number
  detection_types: string[]
  cadence: number
  owner_email: string | null
}

// Regions
export const regionsApi = {
  list: () => apiClient.get<Region[]>('/regions/').then((r) => r.data),
  get: (id: number) => apiClient.get<Region>(`/regions/${id}`).then((r) => r.data),
  create: (payload: RegionCreatePayload) =>
    apiClient.post<Region>('/regions/', payload).then((r) => r.data),
  delete: (id: number) => apiClient.delete(`/regions/${id}`),
}

// Events
export const eventsApi = {
  list: (params?: {
    region_id?: number
    detected_type?: string
    since?: string
    until?: string
    limit?: number
    offset?: number
  }) => apiClient.get<SentinelEvent[]>('/events/', { params }).then((r) => r.data),
  get: (id: number) => apiClient.get<SentinelEvent>(`/events/${id}`).then((r) => r.data),
}

// Alerts
export const alertsApi = {
  subscribe: (payload: { region_id: number; email?: string; slack_webhook?: string }) =>
    apiClient.post<AlertSubscription>('/alerts/subscribe', payload).then((r) => r.data),
  unsubscribe: (subscription_id: number) =>
    apiClient.delete('/alerts/unsubscribe', { data: { subscription_id } }),
}

// Stats
export interface Stats {
  total_regions: number
  total_events: number
  total_subscriptions: number
  events_7d: number
  events_30d: number
  events_by_type: Record<string, number>
  events_by_type_7d: Record<string, number>
  confirmed_events: number
}

export const statsApi = {
  get: () => apiClient.get<Stats>('/stats/').then((r) => r.data),
}

// Admin
export const adminApi = {
  triggerScan: (regionId: number) =>
    apiClient.post<{ queued: boolean; task_id: string }>(`/admin/scan/${regionId}`).then((r) => r.data),
  triggerScanAll: () =>
    apiClient.post<{ queued: boolean; task_id: string }>('/admin/scan-all').then((r) => r.data),
}

// Event feedback
export const feedbackApi = {
  submit: (eventId: number, is_false_positive: boolean) =>
    apiClient
      .patch<SentinelEvent>(`/events/${eventId}/feedback`, { is_false_positive })
      .then((r) => r.data),
}
