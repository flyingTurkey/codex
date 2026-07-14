export type DocumentStates = DocumentState[] | null
export type DocumentState = 'UPDATED' | 'RE_REVIEW_PENDING' | 'WITHDRAWN' | 'SOURCE_UNAVAILABLE'
export type EvidenceCount = number | null
export type IncidentStatus =
  | 'UNVERIFIED_LEAD'
  | 'INITIAL_OFFICIAL_REPORT'
  | 'UNDER_INVESTIGATION'
  | 'FINAL_INVESTIGATION_REPORT'
  | 'ENFORCEMENT_DECISION'
  | 'RECTIFICATION_FOLLOW_UP'
  | 'CLOSED'
  | 'CORRECTED'
  | 'WITHDRAWN'
export type ItemId = string
export type OriginalUrl = string
export type PublicationRevisionId = string | null
export type EventRelation = 'FOLLOW_UP' | 'INVESTIGATES' | 'PENALIZES' | 'RECTIFIES' | 'CORRECTS'
export type SafetyCaseReportStage =
  'INITIAL_REPORT' | 'FOLLOW_UP_REPORT' | 'FINAL_INVESTIGATION' | 'ENFORCEMENT' | 'RECTIFICATION'
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SourceName = string
export type SourcePublishedAt = string | null
export type Title = string

export interface EventItem {
  document_states?: DocumentStates
  evidence_count?: EvidenceCount
  incident_status: IncidentStatus
  item_id: ItemId
  original_url: OriginalUrl
  publication_revision_id: PublicationRevisionId
  relation_type?: EventRelation | null
  report_stage: SafetyCaseReportStage
  review_status: ReviewStatus
  source_name: SourceName
  source_published_at: SourcePublishedAt
  title: Title
}
