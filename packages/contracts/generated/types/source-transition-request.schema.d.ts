export type Reason = string
/**
 * Deprecated V1 source state retained only for compatibility projections.
 */
export type SourceState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'FIXTURE_TEST' | 'APPROVED' | 'ACTIVE'

export interface SourceTransitionRequest {
  reason: Reason
  target_state: SourceState
}
