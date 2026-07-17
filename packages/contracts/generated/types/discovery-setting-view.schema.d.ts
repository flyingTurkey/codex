export type AutomationEnabled = boolean
export type BaiduStatus = 'DISABLED' | 'KEY_MISSING' | 'AVAILABLE' | 'BUDGET_EXHAUSTED'
export type DiscoveryIntervalSeconds = number
export type NextRunAt = string | null
export type UpdatedAt = string

export interface DiscoverySettingView {
  automation_enabled: AutomationEnabled
  baidu_status: BaiduStatus
  discovery_interval_seconds: DiscoveryIntervalSeconds
  next_run_at?: NextRunAt
  updated_at: UpdatedAt
}
