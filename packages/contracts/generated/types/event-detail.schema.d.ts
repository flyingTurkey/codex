export type ClaimId = string
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
export type SafetyCaseFactField =
  | 'OCCURRED_AT'
  | 'REGION'
  | 'PROJECT_NAME'
  | 'HAZARD_TYPE'
  | 'ENGINEERING_TYPE'
  | 'DEATH_COUNT'
  | 'INJURY_COUNT'
  | 'LOSS_AMOUNT_MINOR'
  | 'OFFICIAL_DIRECT_CAUSES'
  | 'RESPONSIBILITY_FINDINGS'
  | 'CORRECTIVE_ACTIONS'
export type Label = string
export type ReviewedAt = string
export type SourceItemId = string
export type Status = 'CONFIRMED'
export type Unit = string | null
export type Value = string | number | string[]
export type ConfirmedFacts = ConfirmedFact[]
export type EngineeringType = string | null
export type HazardType = string | null
export type Id = string
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
export type OccurredAt = string | null
export type PreventionMeasureTag =
  | 'HAZARD_IDENTIFICATION'
  | 'MONITORING_AND_EARLY_WARNING'
  | 'INSPECTION_AND_MAINTENANCE'
  | 'DESIGN_REVIEW'
  | 'CONSTRUCTION_QUALITY_CONTROL'
  | 'EMERGENCY_PREPAREDNESS'
  | 'TRAFFIC_OPERATION_RISK_CONTROL'
  | 'RESPONSIBILITY_AND_OVERSIGHT'
export type PreventionMeasureTags = PreventionMeasureTag[]
export type ProjectName = string | null
export type RectificationHasOpenIssues = boolean | null
export type Region = string | null
export type EventId = string
export type FromItemId = string
export type Id1 = string
export type EventRelation = 'FOLLOW_UP' | 'INVESTIGATES' | 'PENALIZES' | 'RECTIFIES' | 'CORRECTS'
export type ReviewedAt1 = string
export type ReviewedBy = string
export type ToItemId = string
export type Relations = EventRelationView[]
export type SimilarScenarioTag =
  | 'HIGHWAY_OPERATION_GEOLOGICAL_RISK'
  | 'ROADBED_SLOPE_INSTABILITY'
  | 'BRIDGE_APPROACH_TRANSITION'
  | 'EXTREME_WEATHER_EXPOSURE'
  | 'TEMPORARY_STRUCTURE_FAILURE'
  | 'TUNNEL_GEOLOGICAL_RISK'
export type SimilarScenarioTags = SimilarScenarioTag[]
export type EventId1 = string
export type DocumentStates = DocumentState[] | null
export type DocumentState = 'UPDATED' | 'RE_REVIEW_PENDING' | 'WITHDRAWN' | 'SOURCE_UNAVAILABLE'
export type EvidenceCount = number | null
export type ItemId = string
export type OriginalUrl = string
export type PublicationRevisionId = string | null
export type SafetyCaseReportStage =
  'INITIAL_REPORT' | 'FOLLOW_UP_REPORT' | 'FINAL_INVESTIGATION' | 'ENFORCEMENT' | 'RECTIFICATION'
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SourceName = string
export type SourcePublishedAt = string | null
export type Title = string
export type Items = EventItem[]
export type Title1 = string
export type ClaimId1 = string | null
export type ConflictId = string | null
export type DisplayValue = '待核实'
export type EvidenceIds1 = string[]
export type Label1 = string
export type Reason = string
export type SourceItemId1 = string
export type Status1 = 'PENDING_REVIEW' | 'CONFLICTING'
export type Value1 = null
export type UnverifiedFacts = UnverifiedFact[]

export interface EventDetail {
  confirmed_facts: ConfirmedFacts
  engineering_type?: EngineeringType
  hazard_type?: HazardType
  id: Id
  incident_status: IncidentStatus
  occurred_at?: OccurredAt
  prevention_measure_tags: PreventionMeasureTags
  project_name?: ProjectName
  rectification_has_open_issues?: RectificationHasOpenIssues
  region?: Region
  relations: Relations
  similar_scenario_tags: SimilarScenarioTags
  timeline: EventTimeline
  title: Title1
  unverified_facts: UnverifiedFacts
}
export interface ConfirmedFact {
  claim_id: ClaimId
  evidence_ids: EvidenceIds
  field: SafetyCaseFactField
  label: Label
  reviewed_at: ReviewedAt
  source_item_id: SourceItemId
  status?: Status
  unit?: Unit
  value: Value
}
export interface EventRelationView {
  event_id: EventId
  from_item_id: FromItemId
  id: Id1
  relation_type: EventRelation
  reviewed_at: ReviewedAt1
  reviewed_by: ReviewedBy
  to_item_id: ToItemId
}
export interface EventTimeline {
  event_id: EventId1
  items: Items
}
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
/**
 * Public-safe unresolved fact: candidate values are intentionally absent.
 */
export interface UnverifiedFact {
  claim_id?: ClaimId1
  conflict_id?: ConflictId
  display_value?: DisplayValue
  evidence_ids?: EvidenceIds1
  field: SafetyCaseFactField
  label: Label1
  reason: Reason
  source_item_id: SourceItemId1
  status: Status1
  value?: Value1
}
