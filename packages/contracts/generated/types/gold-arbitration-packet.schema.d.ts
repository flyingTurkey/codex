export type AnnotationId = string
export type DecisionCode = string
/**
 * @maxItems 100
 */
export type EvidenceIds = string[]
export type LabelValue = string | null
/**
 * @maxItems 100
 */
export type RelatedSampleRefs = string[]
/**
 * @minItems 2
 * @maxItems 2
 */
export type Options = GoldArbitrationOption[]
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

export interface GoldArbitrationPacket {
  options: Options
  task: GoldTaskView
}
export interface GoldArbitrationOption {
  annotation_id: AnnotationId
  decision_code: DecisionCode
  evidence_ids?: EvidenceIds
  label_value?: LabelValue
  related_sample_refs?: RelatedSampleRefs
}
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
