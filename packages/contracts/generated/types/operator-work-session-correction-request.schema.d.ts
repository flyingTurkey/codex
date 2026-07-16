export type ActiveSeconds = number
export type ExpectedVersion = number
export type ReasonCode = 'TIMER_INTERRUPTED' | 'MISSED_STOP' | 'DUPLICATE_SESSION' | 'ADMINISTRATIVE_CORRECTION'

export interface OperatorWorkSessionCorrectionRequest {
  active_seconds: ActiveSeconds
  expected_version: ExpectedVersion
  reason_code: ReasonCode
}
