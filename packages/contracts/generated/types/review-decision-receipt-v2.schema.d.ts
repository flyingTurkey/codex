export type CaseId = string
export type DecisionId = string
export type RecordedAt = string
export type ReprocessingOutboxId = string
export type ReprocessingState = 'QUEUED'
export type Version = number

export interface ReviewDecisionReceiptV2 {
  case_id: CaseId
  decision_id: DecisionId
  recorded_at: RecordedAt
  reprocessing_outbox_id: ReprocessingOutboxId
  reprocessing_state?: ReprocessingState
  version: Version
}
