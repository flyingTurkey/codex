export type EventId = string
export type FirstDiscoveredAt = string
export type OfficialSource = boolean
export type OriginalUrl = string
export type PrimaryIntelligenceType = 'DIGITAL_TRANSFORMATION' | 'SAFETY_INTELLIGENCE' | 'INDUSTRY_UPDATE'
export type ProjectionKind = 'R3_METADATA'
export type ReviewState = 'PENDING_OWNER_REVIEW'
export type SourceName = string
export type SourcePublishedAt = string | null
export type Title = string

export interface EventMetadataProjectionV2 {
  event_id: EventId
  first_discovered_at: FirstDiscoveredAt
  official_source: OfficialSource
  original_url: OriginalUrl
  primary_type: PrimaryIntelligenceType
  projection_kind?: ProjectionKind
  review_state?: ReviewState
  source_name: SourceName
  source_published_at: SourcePublishedAt
  title: Title
}
