export type DiscoveredCount = number | null
export type FailedCount = number | null
export type FetchedCount = number | null
export type Id = string
export type Kind =
  'OWNER_ENABLED' | 'OWNER_DISABLED' | 'AUTO_ENABLED' | 'DISPLAY_NAME_CHANGED' | 'URL_PROBE' | 'COLLECTION_RUN'
export type OccurredAt = string
export type ReasonCode = string | null
export type Status = string
export type StreamId = string | null
/**
 * @maxItems 100
 */
export type Items = PersonalSourceActivityItemView[]
export type NextCursor = string | null
export type DiscoveredCount1 = number
export type FailedCount1 = number
export type FetchedCount1 = number
export type LastRunAt = string | null
export type LastRunStatus = string | null
export type NextRunAt = string | null

export interface PersonalSourceActivityPage {
  items: Items
  next_cursor?: NextCursor
  run_summary: PersonalSourceRunSummaryView
}
export interface PersonalSourceActivityItemView {
  discovered_count?: DiscoveredCount
  failed_count?: FailedCount
  fetched_count?: FetchedCount
  id: Id
  kind: Kind
  occurred_at: OccurredAt
  reason_code?: ReasonCode
  status: Status
  stream_id?: StreamId
}
export interface PersonalSourceRunSummaryView {
  discovered_count?: DiscoveredCount1
  failed_count?: FailedCount1
  fetched_count?: FetchedCount1
  last_run_at?: LastRunAt
  last_run_status?: LastRunStatus
  next_run_at?: NextRunAt
}
