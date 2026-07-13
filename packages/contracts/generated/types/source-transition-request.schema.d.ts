export type Reason = string
export type SourceState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'FIXTURE_TEST' | 'APPROVED' | 'ACTIVE'

export interface SourceTransitionRequest {
  reason: Reason
  target_state: SourceState
}
