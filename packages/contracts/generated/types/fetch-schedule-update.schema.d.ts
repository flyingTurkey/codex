export type DailyByteBudget = number
export type DailyRequestBudget = number
export type ExpectedVersion = number
export type FreshnessSloSeconds = number
export type IntervalSeconds = number
export type RateLimitPerMinute = number
export type Reason = string
export type FetchScheduleStatus = 'ACTIVE' | 'PAUSED' | 'RETIRED'

export interface FetchScheduleUpdate {
  daily_byte_budget: DailyByteBudget
  daily_request_budget: DailyRequestBudget
  expected_version: ExpectedVersion
  freshness_slo_seconds: FreshnessSloSeconds
  interval_seconds: IntervalSeconds
  rate_limit_per_minute: RateLimitPerMinute
  reason: Reason
  status: FetchScheduleStatus
}
