export type OperatorWorkCategory = 'SOURCE_MAINTENANCE' | 'EXCEPTION_HANDLING' | 'R3_REVIEW' | 'COPYRIGHT_CORRECTION'
export type Reason = string
export type SourceId = string | null
export type WindowId = string

export interface OperatorTaskCreateRequest {
  category: OperatorWorkCategory
  reason: Reason
  source_id?: SourceId
  window_id: WindowId
}
