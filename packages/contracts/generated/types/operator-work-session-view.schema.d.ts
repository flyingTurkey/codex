export type ActiveSeconds = number | null
export type ActorId = string
export type OperatorWorkCategory = 'SOURCE_MAINTENANCE' | 'EXCEPTION_HANDLING' | 'R3_REVIEW' | 'COPYRIGHT_CORRECTION'
export type Corrected = boolean
export type Id = string
export type LastActivityAt = string
export type StartedAt = string
export type StoppedAt = string | null
export type TaskId = string
export type Version = number
export type WindowId = string

export interface OperatorWorkSessionView {
  active_seconds?: ActiveSeconds
  actor_id: ActorId
  category: OperatorWorkCategory
  corrected?: Corrected
  id: Id
  last_activity_at: LastActivityAt
  started_at: StartedAt
  stopped_at?: StoppedAt
  task_id: TaskId
  version?: Version
  window_id: WindowId
}
