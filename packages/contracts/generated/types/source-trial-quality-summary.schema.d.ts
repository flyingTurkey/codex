export type ParseFailedCount = number
export type RawCount = number
export type ReadyCount = number
export type ReadyRatioBps = number
export type RejectedRawAttemptCount = number
export type SecurityFailedCount = number

export interface SourceTrialQualitySummary {
  parse_failed_count: ParseFailedCount
  raw_count: RawCount
  ready_count: ReadyCount
  ready_ratio_bps: ReadyRatioBps
  rejected_raw_attempt_count: RejectedRawAttemptCount
  security_failed_count: SecurityFailedCount
}
