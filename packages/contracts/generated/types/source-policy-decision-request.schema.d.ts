export type SourcePolicyDecisionOutcome = 'APPROVED' | 'REJECTED'
export type Reason = string

export interface SourcePolicyDecisionRequest {
  outcome: SourcePolicyDecisionOutcome
  reason: Reason
}
