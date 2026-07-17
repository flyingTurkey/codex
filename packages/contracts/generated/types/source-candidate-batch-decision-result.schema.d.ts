export type DecidedAt = string
export type IdempotentReplay = boolean
export type CandidateId = string
export type SourceCandidateDecisionItemOutcome = 'APPLIED' | 'CONFLICT' | 'REJECTED'
export type ProductionRefetchEnqueued = boolean
export type ReasonCode = string | null
export type SourceId = string | null
export type SourceCandidateStatus =
  'DISCOVERED' | 'QUALIFYING' | 'READY_FOR_DECISION' | 'ENABLED' | 'DISMISSED' | 'BLOCKED' | 'STALE'
/**
 * @minItems 1
 * @maxItems 10
 */
export type Items = SourceCandidateDecisionItemResult[]
export type RuleVersion = string

export interface SourceCandidateBatchDecisionResult {
  decided_at: DecidedAt
  idempotent_replay: IdempotentReplay
  items: Items
  rule_version: RuleVersion
}
export interface SourceCandidateDecisionItemResult {
  candidate_id: CandidateId
  outcome: SourceCandidateDecisionItemOutcome
  production_refetch_enqueued: ProductionRefetchEnqueued
  reason_code?: ReasonCode
  source_id?: SourceId
  status?: SourceCandidateStatus | null
}
