export type ClaimConflictDecisionAction = 'ACCEPT_CANDIDATE' | 'KEEP_CURRENT' | 'MARK_UNRESOLVED'
export type ConflictId = string
export type ResolvedAt = string | null
export type ResolvedClaimId = string | null
export type ClaimConflictStatus = 'PENDING_REVIEW' | 'RESOLVED'

export interface ClaimConflictDecisionResponse {
  action: ClaimConflictDecisionAction
  conflict_id: ConflictId
  resolved_at: ResolvedAt
  resolved_claim_id: ResolvedClaimId
  status: ClaimConflictStatus
}
