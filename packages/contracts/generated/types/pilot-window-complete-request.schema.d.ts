export type ExpectedVersion = number
export type Reason = string

export interface PilotWindowCompleteRequest {
  expected_version: ExpectedVersion
  reason: Reason
}
