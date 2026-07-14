export type Action = 'ACCEPT' | 'REJECT' | 'CONFIRM_UNRESOLVED'
export type Reason = string
export type TargetDocumentId = string | null

export interface ReviewCandidateDecisionRequest {
  action: Action
  reason: Reason
  target_document_id?: TargetDocumentId
}
