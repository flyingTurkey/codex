export type CandidateLabel = string
export type CandidateType = 'MODEL_ALIAS' | 'VERSION_SUCCESSOR' | 'POSSIBLE_DUPLICATE'
export type CandidateVersionId = string
export type CreatedAt = string
export type Id = string
export type IncomingLabel = string
export type IncomingVersionId = string
export type Status = 'PENDING_REVIEW' | 'ACCEPTED' | 'REJECTED'

export interface ProductNormalizationCandidateView {
  candidate_label: CandidateLabel
  candidate_type: CandidateType
  candidate_version_id: CandidateVersionId
  created_at: CreatedAt
  id: Id
  incoming_label: IncomingLabel
  incoming_version_id: IncomingVersionId
  status: Status
}
