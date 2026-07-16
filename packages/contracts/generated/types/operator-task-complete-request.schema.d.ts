export type ExpectedVersion = number
export type Reason = string

export interface OperatorTaskCompleteRequest {
  expected_version: ExpectedVersion
  reason: Reason
}
