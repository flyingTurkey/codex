export type BlockedReason = string | null
export type DocumentVersionId = string | null
export type ErrorCode = string
export type EventId = string | null
export type FailedAt = string
export type Id = string
export type Priority = number
export type ReconstructionStatus = 'REPLAYABLE' | 'NON_REPLAYABLE' | 'BLOCKED'
export type ReplayStatus = string | null
export type RunId = string | null
export type SourceId = string | null
export type TaskKind = string

export interface ReplayTaskView {
  blocked_reason?: BlockedReason
  document_version_id?: DocumentVersionId
  error_code: ErrorCode
  event_id?: EventId
  failed_at: FailedAt
  id: Id
  priority: Priority
  reconstruction_status: ReconstructionStatus
  replay_status?: ReplayStatus
  run_id?: RunId
  source_id?: SourceId
  task_kind: TaskKind
}
