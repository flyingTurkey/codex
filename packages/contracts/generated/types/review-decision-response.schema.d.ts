export type PublicationRevisionId = string | null
export type ReviewTaskId = string
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface ReviewDecisionResponse {
  publication_revision_id: PublicationRevisionId
  review_task_id: ReviewTaskId
  status: ReviewStatus
}
