// Generated from canonical Pydantic contracts. Do not edit directly.

export type HasMore = boolean
export type Items = {
  [k: string]: string | number | boolean | null
}[]
export type NextCursor = string | null

export interface CursorPageDictStrUnionStrIntBoolNoneType {
  has_more: HasMore
  items: Items
  next_cursor?: NextCursor
}

export type Service = 'api'
export type Status = 'ok'
export type Timestamp = string

export interface LivenessResponse {
  service?: Service
  status?: Status
  timestamp: Timestamp
}

export type Detail = string | null
export type Instance = string | null
export type RequestId = string
export type Status = number
export type Title = string
export type Type = string

export interface ProblemDetails {
  detail?: Detail
  instance?: Instance
  request_id: RequestId
  status: Status
  title: Title
  type?: Type
}

export type ErrorCode = ('timeout' | 'unavailable' | 'misconfigured') | null
export type LatencyMs = number
export type Status = 'up' | 'down'
export type Service = 'api'
export type Status1 = 'ready' | 'not_ready'
export type Timestamp = string

export interface ReadinessResponse {
  checks: Checks
  service?: Service
  status: Status1
  timestamp: Timestamp
}
export interface Checks {
  [k: string]: DependencyCheck
}
export interface DependencyCheck {
  error_code?: ErrorCode
  latency_ms: LatencyMs
  status: Status
}

export type ApiVersion = 'v1'
export type ContentSchemaVersion = '1.0.0'

export interface VersionResponse {
  api_version?: ApiVersion
  content_schema_version?: ContentSchemaVersion
}
