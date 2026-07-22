export type CreatedAt = string
export type OwnerExceptionEventType =
  'CREATED' | 'RETRY_REQUESTED' | 'OWNER_ALLOWED' | 'OWNER_DENIED' | 'AUTO_RESOLVED' | 'SOURCE_DISABLED'
export type ExceptionId = string
export type ExpectedVersion = number
export type Id = string
export type IdempotencyKey = string

export interface OwnerExceptionEventView {
  created_at: CreatedAt
  event_type: OwnerExceptionEventType
  exception_id: ExceptionId
  expected_version: ExpectedVersion
  id: Id
  idempotency_key: IdempotencyKey
}
