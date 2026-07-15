export type FailedTaskId = string
export type Priority = number
export type Reason = string

export interface ReplayRequest {
  failed_task_id: FailedTaskId
  priority?: Priority
  reason: Reason
}
