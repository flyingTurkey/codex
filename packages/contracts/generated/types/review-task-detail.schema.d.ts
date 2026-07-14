export type ClaimType = string
export type DecisionStatus = ('PENDING' | 'ACCEPTED' | 'REJECTED') | null
/**
 * @minItems 1
 */
export type EvidenceIds = [string, ...string[]]
export type Id = string
export type Label = string
export type Value = string
export type Claims = ClaimView[]
export type CharEnd = number | null
export type CharStart = number | null
/**
 * @minItems 1
 */
export type ClaimIds = [string, ...string[]]
export type DocumentVersionId = string | null
export type Excerpt = string
export type ExcerptSha256 = string
export type Id1 = string
export type Locator = (HtmlParagraphLocator | PdfTextLocator | PdfOcrLocator | PdfTableCellLocator) | null
export type CharEnd1 = number
export type CharStart1 = number
export type ParagraphId = string
export type Type = 'HTML_PARAGRAPH'
export type X0 = number
export type X1 = number
export type Y0 = number
export type Y1 = number
export type BlockId = string
export type PageNumber = number
export type Type1 = 'PDF_TEXT'
export type BlockId1 = string
export type ConfidenceBps = number
export type PageNumber1 = number
export type Type2 = 'PDF_OCR'
export type ColumnIndex = number
export type ConfidenceBps1 = number | null
export type PageNumber2 = number
export type RowIndex = number
export type TableCellId = string
export type Type3 = 'PDF_TABLE_CELL'
export type OriginalUrl = string
export type ParagraphId1 = string | null
export type Evidence = EvidenceView[]
export type ActivityAt = string
export type ItemType =
  | 'DIGITAL_CASE'
  | 'JOURNAL_PAPER'
  | 'SOFTWARE_PRODUCT'
  | 'IOT_PRODUCT'
  | 'LOW_ALTITUDE_EQUIPMENT'
  | 'AI_EQUIPMENT'
  | 'SAFETY_REGULATION'
  | 'SAFETY_CASE'
export type DetailAvailable = boolean | null
export type DocumentStates = DocumentState[] | null
export type DocumentState = 'UPDATED' | 'RE_REVIEW_PENDING' | 'WITHDRAWN' | 'SOURCE_UNAVAILABLE'
export type Channel = 'DIGITAL' | 'SAFETY'
export type EvidenceCount = number | null
export type EvidenceStatus = 'WITHHELD' | 'VERIFIED'
export type FirstDiscoveredAt = string
export type HasVersionHistory = boolean | null
export type Id2 = string
export type IsSaved = boolean | null
export type LastUpdatedAt = string | null
export type OneSentenceFact = string | null
export type OriginalUrl1 = string
export type PublicationRevisionId = string | null
export type PublicationStatus = 'PENDING_REVIEW' | 'PUBLISHED' | 'WITHDRAWN'
export type RelevanceReason = string | null
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SourceName = string
export type SourcePublishedAt = string | null
export type SourceRole = string | null
export type Tags = string[] | null
export type Title = string
export type TypeSummary = (SafetyRegulationTypeSummary | SafetyCaseTypeSummary) | null
export type RegulationClassification =
  'LAW' | 'ADMINISTRATIVE_REGULATION' | 'DEPARTMENT_RULE' | 'NORMATIVE_DOCUMENT' | 'STANDARD_OR_GUIDE'
export type DocumentNumber = string
export type IssuingAuthority = string
export type Kind = 'SAFETY_REGULATION'
export type RegulationStatus =
  'DRAFT' | 'NOT_EFFECTIVE' | 'EFFECTIVE' | 'AMENDED' | 'REPEALED' | 'SUPERSEDED' | 'EXPIRED' | 'UNKNOWN'
export type ConflictedFields = CriticalSafetyField[] | null
export type CriticalSafetyField =
  'DEATH_COUNT' | 'INJURY_COUNT' | 'LOSS_AMOUNT_MINOR' | 'OFFICIAL_DIRECT_CAUSES' | 'RESPONSIBILITY_FINDINGS'
export type Deaths = number | null
export type EngineeringType = string | null
export type EventId = string | null
export type HazardType = string | null
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
export type Injuries = number | null
export type Kind1 = 'SAFETY_CASE'
export type LossAmountMinor = number | null
export type LossCurrency = string | null
export type OccurredAt = string | null
/**
 * null means no formal investigation basis; an empty list means formal evidence was reviewed and stated no direct-cause finding
 */
export type OfficialDirectCauses = string[] | null
export type PreventionMeasureTags = PreventionMeasureTag[] | null
export type PreventionMeasureTag =
  | 'HAZARD_IDENTIFICATION'
  | 'MONITORING_AND_EARLY_WARNING'
  | 'INSPECTION_AND_MAINTENANCE'
  | 'DESIGN_REVIEW'
  | 'CONSTRUCTION_QUALITY_CONTROL'
  | 'EMERGENCY_PREPAREDNESS'
  | 'TRAFFIC_OPERATION_RISK_CONTROL'
  | 'RESPONSIBILITY_AND_OVERSIGHT'
/**
 * Reviewed rectification evaluation result; null means not established
 */
export type RectificationHasOpenIssues = boolean | null
export type Region = string | null
export type SafetyCaseReportStage =
  'INITIAL_REPORT' | 'FOLLOW_UP_REPORT' | 'FINAL_INVESTIGATION' | 'ENFORCEMENT' | 'RECTIFICATION'
/**
 * null means no formal investigation or enforcement basis; an empty list means formal evidence was reviewed and stated no responsibility finding
 */
export type ResponsibilityFindings = string[] | null
export type SimilarScenarioTags = SimilarScenarioTag[] | null
export type SimilarScenarioTag =
  | 'HIGHWAY_OPERATION_GEOLOGICAL_RISK'
  | 'ROADBED_SLOPE_INSTABILITY'
  | 'BRIDGE_APPROACH_TRANSITION'
  | 'EXTREME_WEATHER_EXPOSURE'
  | 'TEMPORARY_STRUCTURE_FAILURE'
  | 'TUNNEL_GEOLOGICAL_RISK'
export type AssignedTo = string | null
export type Id3 = string
export type ItemId = string
export type RiskLevel = 'R1' | 'R2' | 'R3' | 'R4'
export type SourceName1 = string
export type SubmittedAt = string
export type SubmittedBy = string
export type Title1 = string

export interface ReviewTaskDetail {
  claims: Claims
  evidence: Evidence
  item: ItemSummary
  task: ReviewTaskSummary
}
export interface ClaimView {
  claim_type: ClaimType
  decision_status?: DecisionStatus
  evidence_ids: EvidenceIds
  id: Id
  label: Label
  value: Value
}
export interface EvidenceView {
  char_end?: CharEnd
  char_start?: CharStart
  claim_ids: ClaimIds
  document_version_id?: DocumentVersionId
  excerpt: Excerpt
  excerpt_sha256: ExcerptSha256
  id: Id1
  locator?: Locator
  original_url: OriginalUrl
  paragraph_id?: ParagraphId1
}
export interface HtmlParagraphLocator {
  char_end: CharEnd1
  char_start: CharStart1
  paragraph_id: ParagraphId
  type: Type
}
export interface PdfTextLocator {
  bbox: PageBoundingBox
  block_id: BlockId
  page_number: PageNumber
  type: Type1
}
/**
 * Rotation-normalized PDF coordinates in integer thousandths of a point.
 */
export interface PageBoundingBox {
  x0: X0
  x1: X1
  y0: Y0
  y1: Y1
}
export interface PdfOcrLocator {
  bbox: PageBoundingBox
  block_id: BlockId1
  confidence_bps: ConfidenceBps
  page_number: PageNumber1
  type: Type2
}
export interface PdfTableCellLocator {
  bbox: PageBoundingBox
  column_index: ColumnIndex
  confidence_bps?: ConfidenceBps1
  page_number: PageNumber2
  row_index: RowIndex
  table_cell_id: TableCellId
  type: Type3
}
export interface ItemSummary {
  activity_at: ActivityAt
  content_type: ItemType
  detail_available?: DetailAvailable
  document_states?: DocumentStates
  domain: Channel
  evidence_count?: EvidenceCount
  evidence_status?: EvidenceStatus | null
  first_discovered_at: FirstDiscoveredAt
  has_version_history?: HasVersionHistory
  id: Id2
  is_saved?: IsSaved
  last_updated_at?: LastUpdatedAt
  one_sentence_fact?: OneSentenceFact
  original_url: OriginalUrl1
  publication_revision_id: PublicationRevisionId
  publication_status?: PublicationStatus | null
  relevance_reason?: RelevanceReason
  review_status: ReviewStatus
  source_name: SourceName
  source_published_at: SourcePublishedAt
  source_role?: SourceRole
  tags?: Tags
  title: Title
  type_summary?: TypeSummary
}
export interface SafetyRegulationTypeSummary {
  classification: RegulationClassification
  document_number: DocumentNumber
  issuing_authority: IssuingAuthority
  kind: Kind
  regulation_status: RegulationStatus
}
/**
 * Reviewed safety-case projection; only ``kind`` is safe for an R3 stub.
 */
export interface SafetyCaseTypeSummary {
  conflicted_fields?: ConflictedFields
  deaths?: Deaths
  engineering_type?: EngineeringType
  event_id?: EventId
  hazard_type?: HazardType
  incident_status?: IncidentStatus | null
  injuries?: Injuries
  kind: Kind1
  loss_amount_minor?: LossAmountMinor
  loss_currency?: LossCurrency
  occurred_at?: OccurredAt
  official_direct_causes?: OfficialDirectCauses
  prevention_measure_tags?: PreventionMeasureTags
  rectification_has_open_issues?: RectificationHasOpenIssues
  region?: Region
  report_stage?: SafetyCaseReportStage | null
  responsibility_findings?: ResponsibilityFindings
  similar_scenario_tags?: SimilarScenarioTags
}
export interface ReviewTaskSummary {
  assigned_to?: AssignedTo
  id: Id3
  item_id: ItemId
  risk_level: RiskLevel
  source_name: SourceName1
  status: ReviewStatus
  submitted_at: SubmittedAt
  submitted_by: SubmittedBy
  title: Title1
}
