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
export type GoldSampleKind = 'DOCUMENT' | 'PAIR' | 'EVENT' | 'CLAIM_EVIDENCE' | 'SEARCH_QUESTION'
export type TaskId = string

export interface GoldAnnotationRequest {
  decision_code: DecisionCode
  evidence_ids?: EvidenceIds
  label_value?: LabelValue
  related_sample_refs?: RelatedSampleRefs
  sample_kind: GoldSampleKind
  task_id: TaskId
}
