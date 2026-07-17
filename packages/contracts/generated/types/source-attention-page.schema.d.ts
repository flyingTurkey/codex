export type HasMore = boolean
export type FirstObservedAt = string
export type LastObservedAt = string
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type AuthorizationBoundary = string
export type SourceStreamAction = 'PAUSE' | 'RESUME' | 'REQUEST_REPAIR' | 'REVOKE'
export type AvailableActions = SourceStreamAction[]
export type CandidateId = string | null
export type CanonicalUrl = string
export type ConsecutiveFailureCount = number
export type Id = string
export type InstitutionName = string
export type LastFailureAt = string | null
export type LastSuccessAt = string | null
export type NextFetchAt = string | null
export type RuleVersion = string
export type SourceId = string
export type SourceStreamStatus = 'QUALIFIED' | 'ACTIVE' | 'PAUSED' | 'REVOKED'
export type StreamKey = string
export type UpdatedAt = string
export type Items = SourceAttentionItem[]
export type NextCursor = string | null

export interface SourceAttentionPage {
  has_more: HasMore
  items: Items
  next_cursor?: NextCursor
}
export interface SourceAttentionItem {
  first_observed_at: FirstObservedAt
  last_observed_at: LastObservedAt
  reason_codes: ReasonCodes
  stream: SourceStreamView
}
export interface SourceStreamView {
  authorization_boundary: AuthorizationBoundary
  available_actions?: AvailableActions
  candidate_id: CandidateId
  canonical_url: CanonicalUrl
  consecutive_failure_count?: ConsecutiveFailureCount
  id: Id
  institution_name: InstitutionName
  last_failure_at?: LastFailureAt
  last_success_at?: LastSuccessAt
  next_fetch_at?: NextFetchAt
  rule_version: RuleVersion
  source_id: SourceId
  status: SourceStreamStatus
  stream_key: StreamKey
  updated_at: UpdatedAt
}
