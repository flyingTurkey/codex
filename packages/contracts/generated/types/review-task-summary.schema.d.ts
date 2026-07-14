export type AssignedTo = string | null
export type Id = string
export type ItemId = string
export type RiskLevel = 'R1' | 'R2' | 'R3' | 'R4'
export type SourceName = string
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SubmittedAt = string
export type SubmittedBy = string
export type Title = string

export interface ReviewTaskSummary {
  assigned_to?: AssignedTo
  id: Id
  item_id: ItemId
  risk_level: RiskLevel
  source_name: SourceName
  status: ReviewStatus
  submitted_at: SubmittedAt
  submitted_by: SubmittedBy
  title: Title
}
