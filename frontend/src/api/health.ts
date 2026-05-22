import http from './http'

export interface HealthPayload {
  status: string
  service: string
  version: string
  timestamp: string
}

export function fetchHealth(): Promise<HealthPayload> {
  return http.get('/health')
}
