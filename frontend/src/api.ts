export type Location = { id: number; name: string; barangay: string; latitude: number; longitude: number; description: string }
export type Device = { id: string; name: string; status: string; last_seen: string | null; location: Location }
export type Detection = { id: string; device_id: string; timestamp: string; dog_count: number; confidence: number; review_status: 'pending' | 'reviewed' | 'flagged'; snapshot_path: string | null; source: string; location: Location; device: Device }
export type Summary = { dogs_today: number; detections_today: number; total_detections: number; active_cameras: number; total_cameras: number; pending_reviews: number; locations_monitored: number }
export type Analytics = { daily: { date: string; detections: number; dogs: number }[]; by_location: { location_id: number; name: string; count: number }[] }
export type NewLocation = { name: string; barangay: string; description: string }
export type NewDevice = { id: string; name: string; location_id?: number; new_location?: NewLocation }

const base = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${base}${path}`, init)
  } catch {
    throw new Error('Local service is unavailable. Start the backend on port 8000, then retry.')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  summary: () => request<Summary>('/api/dashboard/summary'),
  detections: () => request<Detection[]>('/api/detections?limit=500'),
  devices: () => request<Device[]>('/api/devices'),
  locations: () => request<Location[]>('/api/locations'),
  analytics: () => request<Analytics>('/api/analytics'),
  review: (id: string, review_status: Detection['review_status']) => request<Detection>(`/api/detections/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ review_status }) }),
  deleteDetection: (id: string) => request<{ deleted_id: string }>(`/api/detections/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearDetections: () => request<{ deleted: number }>('/api/detections', { method: 'DELETE' }),
  createDevice: (payload: NewDevice) => request<Device>('/api/devices', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  simulate: (deviceId = 'CAM-001', dogCount = 2) => request<Detection>(`/api/demo/simulate?device_id=${encodeURIComponent(deviceId)}&dog_count=${dogCount}`, { method: 'POST' }),
  snapshot: (path: string | null) => path ? `${base}${path}` : '',
}
