export type AuthorityLevel = string
export type BytesUsed = number
export type CircuitOpenUntil = string | null
export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN'
export type ConsecutiveFailures = number
export type DailyByteBudget = number
export type DailyRequestBudget = number
export type FreshnessSloSeconds = number
export type IntervalSeconds = number
export type NextRunAt = string
export type RateLimitPerMinute = number
export type RequestsUsed = number
export type SourceId = string
export type FetchScheduleStatus = 'ACTIVE' | 'PAUSED' | 'RETIRED'
export type UpdatedAt = string
export type Version = number

export interface FetchScheduleView {
  authority_level: AuthorityLevel
  bytes_used: BytesUsed
  circuit_open_until?: CircuitOpenUntil
  circuit_state: CircuitState
  consecutive_failures: ConsecutiveFailures
  daily_byte_budget: DailyByteBudget
  daily_request_budget: DailyRequestBudget
  freshness_slo_seconds: FreshnessSloSeconds
  interval_seconds: IntervalSeconds
  next_run_at: NextRunAt
  rate_limit_per_minute: RateLimitPerMinute
  requests_used: RequestsUsed
  source_id: SourceId
  status: FetchScheduleStatus
  updated_at: UpdatedAt
  version: Version
}
