export type OwnerExceptionEventType =
  'CREATED' | 'RETRY_REQUESTED' | 'OWNER_ALLOWED' | 'OWNER_DENIED' | 'AUTO_RESOLVED' | 'SOURCE_DISABLED'
export type ExceptionId = string
export type ExpectedVersion = number

export interface OwnerExceptionCommand {
  event_type: OwnerExceptionEventType
  exception_id: ExceptionId
  expected_version: ExpectedVersion
}
