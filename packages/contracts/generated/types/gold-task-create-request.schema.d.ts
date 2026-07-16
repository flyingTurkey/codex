/**
 * @minItems 1
 * @maxItems 2
 */
export type AssignedAnnotatorIds = string[]
export type CriticalSafety = boolean
export type Channel = 'DIGITAL' | 'SAFETY'
export type ProductionDecisionId = string
export type Reason = string
export type GoldSampleKind = 'DOCUMENT' | 'PAIR' | 'EVENT' | 'CLAIM_EVIDENCE' | 'SEARCH_QUESTION'
export type SampleRef = string
export type SecondaryReviewRequired = boolean
export type SourceCode = string

export interface GoldTaskCreateRequest {
  assigned_annotator_ids: AssignedAnnotatorIds
  critical_safety?: CriticalSafety
  domain: Channel
  production_decision_id: ProductionDecisionId
  reason: Reason
  sample_kind: GoldSampleKind
  sample_ref: SampleRef
  secondary_review_required?: SecondaryReviewRequired
  source_code: SourceCode
}
