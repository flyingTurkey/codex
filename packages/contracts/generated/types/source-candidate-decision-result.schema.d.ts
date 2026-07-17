export type CandidateId = string
export type DecidedAt = string
export type IdempotentReplay = boolean
export type ProductionRefetchEnqueued = boolean
export type SourceId = string | null
export type SourceCandidateStatus =
  'DISCOVERED' | 'QUALIFYING' | 'READY_FOR_DECISION' | 'ENABLED' | 'DISMISSED' | 'BLOCKED' | 'STALE'

export interface SourceCandidateDecisionResult {
  candidate_id: CandidateId
  decided_at: DecidedAt
  idempotent_replay: IdempotentReplay
  production_refetch_enqueued: ProductionRefetchEnqueued
  source_id?: SourceId
  status: SourceCandidateStatus
}
