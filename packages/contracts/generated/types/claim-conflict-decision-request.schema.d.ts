export type ClaimConflictDecisionAction = 'ACCEPT_CANDIDATE' | 'KEEP_CURRENT' | 'MARK_UNRESOLVED'
export type Reason = string

export interface ClaimConflictDecisionRequest {
  action: ClaimConflictDecisionAction
  reason: Reason
}
