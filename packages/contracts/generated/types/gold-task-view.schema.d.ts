export type AssignedAt = string
export type CriticalSafety = boolean
export type Channel = 'DIGITAL' | 'SAFETY'
export type Id = string
export type ProductionDecisionId = string
export type GoldSampleKind = 'DOCUMENT' | 'PAIR' | 'EVENT' | 'CLAIM_EVIDENCE' | 'SEARCH_QUESTION'
export type SampleRef = string
export type SecondaryReviewRequired = boolean
export type SourceCode = string
export type Status = 'ASSIGNED' | 'SUBMITTED' | 'DISAGREEMENT' | 'ARBITRATED' | 'FROZEN'

export interface GoldTaskView {
  assigned_at: AssignedAt
  critical_safety: CriticalSafety
  domain: Channel
  id: Id
  production_decision_id: ProductionDecisionId
  sample_kind: GoldSampleKind
  sample_ref: SampleRef
  secondary_review_required: SecondaryReviewRequired
  source_code: SourceCode
  status: Status
}
