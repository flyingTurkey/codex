export type Id = string
export type PublishedAt = string | null
export type ReportDate = string
export type RequiresRegeneration = boolean
export type AutomaticResultType = ('EVIDENCE_FACT' | 'AI_JUDGMENT' | 'UNVERIFIED_AI' | 'AI_PROCESSING_FAILED') | null
export type CurrentState = 'PUBLISHED' | 'WITHDRAWN' | 'SOURCE_UNAVAILABLE'
export type EventId = string | null
export type EventRevisionId = string | null
export type ItemId = string | null
export type OriginalUrl = string
export type Position = number
export type PublicationRevisionId = string | null
export type SignalId = string | null
export type Summary = string | null
export type Title = string
export type Items = DailyReportItem[]
export type Kind =
  | 'TODAY_HIGHLIGHTS'
  | 'DIGITAL_SELECTED'
  | 'SAFETY_HIGHLIGHTS'
  | 'WATCHLIST'
  | 'SOURCE_ANOMALIES'
  | 'EVIDENCE_FACTS'
  | 'AI_JUDGMENTS'
  | 'UNVERIFIED_AI'
  | 'AI_PROCESSING_FAILURES'
export type Title1 = string
export type Sections = DailyReportSection[]
export type SnapshotAt = string
export type Status = 'DRAFT' | 'PUBLISHED'

export interface DailyReport {
  id: Id
  published_at?: PublishedAt
  report_date: ReportDate
  requires_regeneration: RequiresRegeneration
  sections: Sections
  snapshot_at: SnapshotAt
  status: Status
}
export interface DailyReportSection {
  items: Items
  kind: Kind
  title: Title1
}
export interface DailyReportItem {
  automatic_result_type?: AutomaticResultType
  current_state: CurrentState
  event_id?: EventId
  event_revision_id?: EventRevisionId
  item_id?: ItemId
  original_url: OriginalUrl
  position: Position
  publication_revision_id?: PublicationRevisionId
  signal_id?: SignalId
  summary?: Summary
  title: Title
}
