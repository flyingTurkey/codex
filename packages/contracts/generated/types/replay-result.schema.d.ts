export type FailedTaskId = string
export type Id = string
export type Priority = number
export type Status = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
export type TaskKind = string

export interface ReplayResult {
  failed_task_id: FailedTaskId
  id: Id
  priority: Priority
  status: Status
  task_kind: TaskKind
}
