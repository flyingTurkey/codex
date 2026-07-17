export type AutoEnableLimit = number
export type AutoEnableRemaining = number
export type AutoEnableUsed = number
export type LocalDate = string
export type ProbeLimit = number
export type ProbeRemaining = number
export type ProbeUsed = number

export interface DiscoveryDailyUsageView {
  auto_enable_limit?: AutoEnableLimit
  auto_enable_remaining?: AutoEnableRemaining
  auto_enable_used: AutoEnableUsed
  local_date: LocalDate
  probe_limit?: ProbeLimit
  probe_remaining?: ProbeRemaining
  probe_used: ProbeUsed
}
