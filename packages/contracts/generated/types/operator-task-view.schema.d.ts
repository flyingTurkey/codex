export type AssignedTo = string
export type OperatorWorkCategory = 'SOURCE_MAINTENANCE' | 'EXCEPTION_HANDLING' | 'R3_REVIEW' | 'COPYRIGHT_CORRECTION'
export type CompletedAt = string | null
export type CompletedBy = string | null
export type CreatedAt = string
export type CreatedBy = string
export type Id = string
export type SourceId = string | null
export type StartedAt = string | null
export type OperatorTaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED'
export type Version = number
export type WindowId = string

export interface OperatorTaskView {
  assigned_to: AssignedTo
  category: OperatorWorkCategory
  completed_at?: CompletedAt
  completed_by?: CompletedBy
  created_at: CreatedAt
  created_by: CreatedBy
  id: Id
  source_id?: SourceId
  started_at?: StartedAt
  status: OperatorTaskStatus
  version?: Version
  window_id: WindowId
}
