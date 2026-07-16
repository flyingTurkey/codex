export type AnnotatorId = string
export type DecisionCode = string
export type Id = string
export type GoldSampleKind = 'DOCUMENT' | 'PAIR' | 'EVENT' | 'CLAIM_EVIDENCE' | 'SEARCH_QUESTION'
export type Status = 'SUBMITTED' | 'SUPERSEDED'
export type SubmittedAt = string
export type TaskId = string

export interface GoldAnnotationView {
  annotator_id: AnnotatorId
  decision_code: DecisionCode
  id: Id
  sample_kind: GoldSampleKind
  status: Status
  submitted_at: SubmittedAt
  task_id: TaskId
}
