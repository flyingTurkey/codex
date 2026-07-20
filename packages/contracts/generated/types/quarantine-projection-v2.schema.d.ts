export type CaseId = string
export type EventId = string | null
export type FirstDiscoveredAt = string | null
export type IsolationReason = string
export type OfficialSource = boolean
export type OriginalUrl = string
export type PrimaryIntelligenceType = 'DIGITAL_TRANSFORMATION' | 'SAFETY_INTELLIGENCE' | 'INDUSTRY_UPDATE'
export type ProjectionKind = 'QUARANTINE'
export type SourcePublishedAt = string | null
export type Title = string

export interface QuarantineProjectionV2 {
  case_id: CaseId
  event_id?: EventId
  first_discovered_at: FirstDiscoveredAt
  isolation_reason: IsolationReason
  official_source: OfficialSource
  original_url: OriginalUrl
  primary_type?: PrimaryIntelligenceType | null
  projection_kind?: ProjectionKind
  source_published_at: SourcePublishedAt
  title: Title
}
