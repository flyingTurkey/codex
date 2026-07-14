export type CandidateClaimId = string
export type CandidateValue = string | number | string[]
export type CurrentClaimId = string | null
export type CurrentValue = string | number | string[] | null
export type DetectedAt = string
export type EventId = string
export type CriticalSafetyField =
  'DEATH_COUNT' | 'INJURY_COUNT' | 'LOSS_AMOUNT_MINOR' | 'OFFICIAL_DIRECT_CAUSES' | 'RESPONSIBILITY_FINDINGS'
export type Id = string
export type ResolutionReason = string | null
export type ResolvedAt = string | null
export type ResolvedBy = string | null
export type ResolvedClaimId = string | null
export type ClaimConflictStatus = 'PENDING_REVIEW' | 'RESOLVED'

export interface ClaimConflict {
  candidate_claim_id: CandidateClaimId
  candidate_value: CandidateValue
  current_claim_id: CurrentClaimId
  current_value: CurrentValue
  detected_at: DetectedAt
  event_id: EventId
  field: CriticalSafetyField
  id: Id
  resolution_reason?: ResolutionReason
  resolved_at?: ResolvedAt
  resolved_by?: ResolvedBy
  resolved_claim_id?: ResolvedClaimId
  status: ClaimConflictStatus
}
