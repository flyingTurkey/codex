export type Action = string
export type CorrectionId = string
export type EventId = string
export type EventVersion = number
export type ProjectionGeneration = number

export interface OwnerRelationshipCorrectionResponse {
  action: Action
  correction_id: CorrectionId
  event_id: EventId
  event_version: EventVersion
  projection_generation: ProjectionGeneration
}
