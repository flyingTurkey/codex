export type ActorId = string
export type CreatedAt = string
export type EventType = string
export type Id = string
export type Reason = string
export type RequestId = string

export interface SourceAuditEventView {
  actor_id: ActorId
  created_at: CreatedAt
  event_type: EventType
  id: Id
  reason: Reason
  request_id: RequestId
}
