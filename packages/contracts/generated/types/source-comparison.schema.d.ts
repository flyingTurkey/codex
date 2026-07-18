export type EventId = string
export type IndependentSourceCount = number
export type AcceptedClaimCount = number
export type EvidenceCount = number
export type ItemId = string
export type LineageRoot = string
export type OrganizationKey = string
export type OriginalUrl = string
export type SourceLineageRole =
  | 'ORIGINAL'
  | 'REPRINT'
  | 'MIRROR'
  | 'INDEPENDENT_REPORT'
  | 'VENDOR_STATEMENT'
  | 'MEDIA_REPORT'
  | 'INDEPENDENT_VERIFICATION'
export type SourceName = string
export type SourcePublishedAt = string | null
export type Sources = SourceComparisonEntry[]

export interface SourceComparison {
  event_id: EventId
  independent_source_count: IndependentSourceCount
  sources: Sources
}
export interface SourceComparisonEntry {
  accepted_claim_count: AcceptedClaimCount
  evidence_count: EvidenceCount
  item_id: ItemId
  lineage_root: LineageRoot
  organization_key: OrganizationKey
  original_url: OriginalUrl
  role: SourceLineageRole
  source_name: SourceName
  source_published_at?: SourcePublishedAt
}
