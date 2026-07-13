export type ErrorCode = ('timeout' | 'unavailable' | 'misconfigured') | null
export type LatencyMs = number
export type Status = 'up' | 'down'
export type Service = 'api'
export type Status1 = 'ready' | 'not_ready'
export type Timestamp = string

export interface ReadinessResponse {
  checks: Checks
  service?: Service
  status: Status1
  timestamp: Timestamp
}
export interface Checks {
  [k: string]: DependencyCheck
}
export interface DependencyCheck {
  error_code?: ErrorCode
  latency_ms: LatencyMs
  status: Status
}
