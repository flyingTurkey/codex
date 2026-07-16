export type ExpectedVersion = number
export type Reason = string

export interface PilotWindowStartRequest {
  expected_version: ExpectedVersion
  reason: Reason
}
