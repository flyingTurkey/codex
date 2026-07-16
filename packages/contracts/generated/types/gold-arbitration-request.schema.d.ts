export type Reason = string
export type SelectedAnnotationId = string
export type TaskId = string

export interface GoldArbitrationRequest {
  reason: Reason
  selected_annotation_id: SelectedAnnotationId
  task_id: TaskId
}
