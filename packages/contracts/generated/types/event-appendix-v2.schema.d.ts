export type AlgorithmVersion = string
export type CreatedAt = string
export type Id = string
export type InputFingerprintSha256 = string
export type AutomaticRelationshipKind =
  | 'DUPLICATE'
  | 'SAME_EVENT'
  | 'FOLLOW_UP_OF'
  | 'INVESTIGATES'
  | 'MODEL_ALIAS'
  | 'VERSION_SUCCESSOR'
  | 'TOPIC'
  | 'RELATED_CONTENT'
export type ModelVersion = string | null
/**
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type RelationshipKey = string
export type ScoreBps = number
export type SourceItemId = string
export type Status = 'ACTIVE' | 'INVALIDATED' | 'WITHDRAWN' | 'SUPERSEDED'
export type TargetItemId = string
/**
 * @maxItems 500
 */
export type AutomaticRelationships = AutomaticRelationshipView[]
/**
 * @maxItems 20
 */
export type FailureReasonCodes = string[]
/**
 * @maxItems 10
 */
export type CurrentLimitations = string[]
/**
 * @maxItems 10
 */
export type PotentialEngineeringScenarios = string[]
/**
 * @maxItems 10
 */
export type PotentialIndustryImpacts = string[]
/**
 * @maxItems 10
 */
export type QuestionsToVerify = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type UsedClaimIds = string[]
export type WhyWorthAttention = string
export type OriginalUrl = string
export type ResultType = 'EVIDENCE_FACT' | 'AI_JUDGMENT' | 'UNVERIFIED_AI' | 'AI_PROCESSING_FAILED'
export type SignalId = string
export type Title = string
/**
 * @maxItems 100
 */
export type AutomaticResults = EventAutomaticResultView[]
export type ClaimType = string
export type DecisionStatus = ('PENDING' | 'ACCEPTED' | 'REJECTED') | null
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
export type Id1 = string
export type Label = string
export type Value = string
/**
 * @maxItems 500
 */
export type Claims = ClaimView[]
export type HeavyContent = boolean
export type TotalItems = number
/**
 * @maxItems 6
 */
export type TruncatedSections = (
  'CLAIMS' | 'EVIDENCE' | 'AUTOMATIC_RESULTS' | 'REVIEWED_RELATIONSHIPS' | 'AUTOMATIC_RELATIONSHIPS' | 'CORRECTIONS'
)[]
/**
 * @minItems 1
 * @maxItems 3
 */
export type Affects = ('SOURCE_EXCERPT' | 'AI_SUMMARY' | 'RELATIONSHIPS')[]
export type Description = string
export type DocumentVersionId = string | null
export type Id2 = string
export type Kind =
  | 'DOCUMENT_VERSION_CHANGED'
  | 'ACCEPTED_CLAIMS_CHANGED'
  | 'SOURCE_WITHDRAWN'
  | 'SOURCE_CORRECTED'
  | 'RELATION_CORRECTED'
export type OccurredAt = string
/**
 * @maxItems 100
 */
export type Corrections = AppendixCorrectionV2[]
export type EventId = string
export type CharEnd = number | null
export type CharStart = number | null
/**
 * @minItems 1
 */
export type ClaimIds = string[]
export type DocumentVersionId1 = string | null
export type Excerpt = string
export type ExcerptSha256 = string
export type Id3 = string
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
export type OriginalUrl1 = string
export type ParagraphId1 = string | null
/**
 * @maxItems 500
 */
export type Evidence = EvidenceView[]
export type EventId1 = string
export type FromItemId = string
export type SafetyCaseReportStage =
  'INITIAL_REPORT' | 'FOLLOW_UP_REPORT' | 'FINAL_INVESTIGATION' | 'ENFORCEMENT' | 'RECTIFICATION'
export type Id4 = string
export type EventRelation = 'FOLLOW_UP' | 'INVESTIGATES' | 'PENALIZES' | 'RECTIFIES' | 'CORRECTS'
export type ReviewedAt = string
export type ReviewedBy = string | null
export type ToItemId = string
/**
 * @maxItems 500
 */
export type Relationships = ReviewedRelationshipV2[]
export type CaseId = string
export type Href = string
export type ReviewHref = '/review'

export interface EventAppendixV2 {
  automatic_relationships?: AutomaticRelationships
  automatic_results?: AutomaticResults
  claims?: Claims
  content_summary?: AppendixContentSummaryV2
  corrections?: Corrections
  event_id: EventId
  evidence?: Evidence
  relationships?: Relationships
  review_context?: AppendixReviewContextV2 | null
  review_href?: ReviewHref
}
export interface AutomaticRelationshipView {
  algorithm_version: AlgorithmVersion
  created_at: CreatedAt
  id: Id
  input_fingerprint_sha256: InputFingerprintSha256
  kind: AutomaticRelationshipKind
  model_version?: ModelVersion
  reason_codes: ReasonCodes
  relationship_key: RelationshipKey
  score_bps: ScoreBps
  source_item_id: SourceItemId
  status: Status
  target_item_id: TargetItemId
}
export interface EventAutomaticResultView {
  failure_reason_codes?: FailureReasonCodes
  judgment?: AiJudgmentSignal | null
  original_url: OriginalUrl
  result_type: ResultType
  signal_id: SignalId
  title: Title
}
export interface AiJudgmentSignal {
  current_limitations?: CurrentLimitations
  potential_engineering_scenarios?: PotentialEngineeringScenarios
  potential_industry_impacts?: PotentialIndustryImpacts
  questions_to_verify?: QuestionsToVerify
  used_claim_ids: UsedClaimIds
  why_worth_attention: WhyWorthAttention
}
export interface ClaimView {
  claim_type: ClaimType
  decision_status?: DecisionStatus
  evidence_ids: EvidenceIds
  id: Id1
  label: Label
  value: Value
}
export interface AppendixContentSummaryV2 {
  heavy_content?: HeavyContent
  total_items?: TotalItems
  truncated_sections?: TruncatedSections
}
export interface AppendixCorrectionV2 {
  affects: Affects
  description: Description
  document_version_id?: DocumentVersionId
  id: Id2
  kind: Kind
  occurred_at: OccurredAt
}
export interface EvidenceView {
  char_end?: CharEnd
  char_start?: CharStart
  claim_ids: ClaimIds
  document_version_id?: DocumentVersionId1
  excerpt: Excerpt
  excerpt_sha256: ExcerptSha256
  id: Id3
  locator?: Locator
  original_url: OriginalUrl1
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
export interface ReviewedRelationshipV2 {
  event_id: EventId1
  from_item_id: FromItemId
  from_stage?: SafetyCaseReportStage | null
  id: Id4
  relation_type: EventRelation
  reviewed_at: ReviewedAt
  reviewed_by?: ReviewedBy
  to_item_id: ToItemId
  to_stage?: SafetyCaseReportStage | null
}
export interface AppendixReviewContextV2 {
  case_id: CaseId
  href: Href
}
