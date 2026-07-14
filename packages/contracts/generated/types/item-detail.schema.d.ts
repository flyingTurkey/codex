export type Claims = ClaimView[] | null
export type ClaimType = string
/**
 * @minItems 1
 */
export type EvidenceIds = [string, ...string[]]
export type Id = string
export type Label = string
export type Value = string
export type Evidence = EvidenceView[] | null
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
export type RegulationClassification =
  'LAW' | 'ADMINISTRATIVE_REGULATION' | 'DEPARTMENT_RULE' | 'NORMATIVE_DOCUMENT' | 'STANDARD_OR_GUIDE'
export type DocumentNumber = string
export type IssuingAuthority = string
export type Kind = 'SAFETY_REGULATION'
export type RegulationStatus =
  'DRAFT' | 'NOT_EFFECTIVE' | 'EFFECTIVE' | 'AMENDED' | 'REPEALED' | 'SUPERSEDED' | 'EXPIRED' | 'UNKNOWN'
export type Code = string
export type Level = 'info' | 'warning' | 'error'
export type Message = string

export interface ItemDetail {
  claims?: Claims
  evidence?: Evidence
  item: ItemSummary
  notice?: FeedNotice | null
}
export interface ClaimView {
  claim_type: ClaimType
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
  type_summary?: TypeSummary | null
}
export interface TypeSummary {
  classification: RegulationClassification
  document_number: DocumentNumber
  issuing_authority: IssuingAuthority
  kind: Kind
  regulation_status: RegulationStatus
}
export interface FeedNotice {
  code: Code
  level: Level
  message: Message
}
