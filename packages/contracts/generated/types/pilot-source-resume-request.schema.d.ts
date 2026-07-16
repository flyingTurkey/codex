export type ExpectedVersion = number
export type Reason = string

export interface PilotSourceResumeRequest {
  expected_version: ExpectedVersion
  reason: Reason
}
