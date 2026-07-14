export type CandidateId = string
export type RequiresHumanReview = true
export type Status = 'PENDING_REVIEW'

export interface EventCandidateGenerationResponse {
  candidate_id: CandidateId
  requires_human_review: RequiresHumanReview
  status: Status
}
