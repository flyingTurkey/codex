export type Claims = ClaimView[] | null
export type ClaimType = string
export type DecisionStatus = ('PENDING' | 'ACCEPTED' | 'REJECTED') | null
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
export type Id = string
export type Label = string
export type Value = string
export type AiShortComment = null
export type Applicability = string[]
/**
 * @maxItems 30
 */
export type ApplicationScenarios = string[]
export type Attribution = string
/**
 * @minItems 1
 */
export type EvidenceIds1 = string[]
export type Id1 = string
export type IndependentEvidenceIds = string[]
export type MetricName = string | null
export type NumericValue = string | null
export type Statement = string
export type Unit = string | null
export type OutcomeVerification = 'CLAIMED' | 'VERIFIED'
export type ClaimedOutcomes = DigitalCaseOutcome[]
export type DeploymentScale = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains = string[]
export type ClaimId = string
export type DigitalCaseEntityType = 'ORGANIZATION' | 'TECHNOLOGY' | 'PROJECT'
export type Id2 = string
export type Name = string
export type RelationType = string
export type Entities = DigitalCaseEntity[]
/**
 * @maxItems 20
 */
export type LifecycleStages = string[]
export type Limitations = string[]
export type MaturityLevel =
  | 'CONCEPT'
  | 'LAB_PROTOTYPE'
  | 'ENGINEERING_PROTOTYPE'
  | 'PILOT'
  | 'SINGLE_PROJECT_PRODUCTION'
  | 'MULTI_PROJECT_REPLICATION'
  | 'ENTERPRISE_SCALE'
  | 'UNKNOWN'
export type RecommendedAction = 'READ_ORIGINAL' | 'SAVE' | 'FOLLOW' | 'TECHNICAL_RESEARCH'
export type RecommendedActions = RecommendedAction[]
export type ReplicationConditions = string[]
export type Risks = string[]
/**
 * @maxItems 50
 */
export type TechnologyTags = string[]
export type VerifiedOutcomes = DigitalCaseOutcome[]
export type Evidence = EvidenceView[] | null
export type CharEnd = number | null
export type CharStart = number | null
/**
 * @minItems 1
 */
export type ClaimIds = string[]
export type DocumentVersionId = string | null
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
export type Id4 = string
export type IsSaved = boolean | null
export type LastUpdatedAt = string | null
export type OneSentenceFact = string | null
export type OriginalUrl1 = string
export type PublicationRevisionId = string | null
export type PublicationStatus = 'PENDING_REVIEW' | 'PUBLISHED' | 'WITHDRAWN'
export type RelevanceReason = string | null
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type CalculatedAt = string
export type ScoreDimension =
  'RELEVANCE' | 'AUTHORITY' | 'IMPACT' | 'NOVELTY' | 'TIMELINESS' | 'EVIDENCE' | 'CONFIDENCE' | 'HEAT'
export type Code = string
export type Explanation = string
export type Label1 = string
export type Points = number
/**
 * @maxItems 20
 */
export type Features = ScoreFeature[]
export type Overridden = boolean
export type OverrideReason = string | null
export type RawScore = number
export type RuleVersion = 'scoring-v1.0.0'
export type Score = number
export type SourceName = string
export type SourcePublishedAt = string | null
export type SourceRole = string | null
export type Tags = string[] | null
export type Title = string
export type TypeSummary =
  | (
      | SafetyRegulationTypeSummary
      | SafetyCaseTypeSummary
      | DigitalCaseTypeSummary
      | PaperTypeSummary
      | SoftwareProductTypeSummary
      | IotProductTypeSummary
      | LowAltitudeEquipmentTypeSummary
      | AiEquipmentTypeSummary
    )
  | null
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
export type AiShortComment1 = null
/**
 * @maxItems 20
 */
export type ApplicationScenarios1 = string[]
export type DeploymentScale1 = string | null
export type Kind2 = 'DIGITAL_CASE'
export type PublisherClaimLabel = string | null
export type Code1 = 'ENGINEERING_DOMAIN' | 'SICHUAN' | 'SRBG_DIRECT'
export type Label2 = string
export type Points1 = number
/**
 * @minItems 1
 * @maxItems 3
 */
export type Factors = RelevanceFactor[]
export type RuleVersion1 = 'relevance-v1.0.0'
export type Score1 = number
export type DigitalCaseSourceNature = 'GOVERNMENT_CASE_COLLECTION' | 'ENTERPRISE_SELF_REPORT'
export type SrbgRelationship = string
export type PaperAccessLevel = 'METADATA_ONLY' | 'ABSTRACT_ALLOWED' | 'OPEN_FULLTEXT'
export type AiShortComment2 = null
export type Doi = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains1 = string[]
export type Journal = string | null
export type Kind3 = 'JOURNAL_PAPER'
export type PaperOpenStatus = 'OPEN' | 'CLOSED' | 'UNKNOWN'
export type PaperType = 'ARTICLE' | 'REVIEW' | 'METHOD' | 'CASE_STUDY' | 'OTHER' | 'UNKNOWN'
export type PaperRelationStatus = 'CURRENT' | 'CORRECTED' | 'RETRACTED' | 'WITHDRAWN'
/**
 * @maxItems 50
 */
export type TechnologyTags1 = string[]
export type Year = number | null
/**
 * @maxItems 20
 */
export type DeploymentModes = string[]
export type ProductEvidenceLevel =
  | 'VENDOR_CLAIM_ONLY'
  | 'PROJECT_EVIDENCE'
  | 'RESEARCH_EVIDENCE'
  | 'INDEPENDENT_VALIDATION'
  | 'OFFICIAL_CERTIFICATION'
  | 'UNKNOWN'
/**
 * @maxItems 30
 */
export type Interfaces = string[]
export type Kind4 = 'SOFTWARE_PRODUCT'
export type ModelNo = string | null
export type ProductKind = string
export type ProductName = string
export type PromotionalClaimCount = number
export type VendorName = string
export type VerifiedCapabilityCount = number
export type Version = string | null
/**
 * @maxItems 30
 */
export type Connectivity = string[]
export type Kind5 = 'IOT_PRODUCT'
export type ModelNo1 = string | null
export type ProductKind1 = string
export type ProductName1 = string
export type PromotionalClaimCount1 = number
export type VendorName1 = string
export type VerifiedCapabilityCount1 = number
export type Version1 = string | null
export type Kind6 = 'LOW_ALTITUDE_EQUIPMENT'
export type ModelNo2 = string | null
/**
 * @maxItems 30
 */
export type PayloadTypes = string[]
export type ProductPermitStatus = 'VERIFIED' | 'NOT_REQUIRED' | 'UNKNOWN'
export type PlatformType = string | null
export type ProductKind2 = string
export type ProductName2 = string
export type PromotionalClaimCount2 = number
export type VendorName2 = string
export type VerifiedCapabilityCount2 = number
export type Version2 = string | null
/**
 * @maxItems 30
 */
export type AiTasks = string[]
export type EquipmentForm = string | null
export type Kind7 = 'AI_EQUIPMENT'
export type ModelNo3 = string | null
export type ProductKind3 = string
export type ProductName3 = string
export type ProductionValidation = boolean
export type PromotionalClaimCount3 = number
export type VendorName3 = string
export type VerifiedCapabilityCount3 = number
export type Version3 = string | null
export type Code2 = string
export type Level = 'info' | 'warning' | 'error'
export type Message = string
export type Abstract = string | null
export type AbstractAvailability = 'AVAILABLE' | 'NOT_PROVIDED' | 'LICENCE_UNCLEAR'
/**
 * @maxItems 30
 */
export type Institutions = string[]
export type Name1 = string
export type Orcid = string | null
/**
 * @maxItems 500
 */
export type Authors = PaperAuthor[]
export type Doi1 = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains2 = string[]
/**
 * @maxItems 20
 */
export type Issns = string[]
export type Issue = string | null
export type Journal1 = string | null
/**
 * @maxItems 100
 */
export type Keywords = string[]
export type OpenFulltextUrl = string | null
export type Pages = string | null
/**
 * @minItems 1
 */
export type ClaimIds1 = string[]
/**
 * @maxItems 30
 */
export type Conclusions = string[]
/**
 * @maxItems 30
 */
export type Conditions = string[]
/**
 * @minItems 1
 */
export type EvidenceIds2 = string[]
/**
 * @maxItems 30
 */
export type Limitations1 = string[]
export type Method = string | null
export type ResearchObject = string | null
export type ItemId = string
export type Journal2 = string | null
/**
 * @minItems 1
 * @maxItems 20
 */
export type MatchReasons = string[]
export type Title1 = string
export type Year1 = number | null
/**
 * @maxItems 5
 */
export type SimilarPapers = SimilarPaper[]
/**
 * @maxItems 50
 */
export type TechnologyTags2 = string[]
export type Volume = string | null
export type Year2 = number | null
/**
 * @maxItems 30
 */
export type ApplicationScenarios2 = string[]
export type CurrentVersion = string | null
/**
 * @maxItems 20
 */
export type DeploymentModes1 = string[]
/**
 * @minItems 1
 */
export type EvidenceIds3 = string[]
export type ItemId1 = string
export type Title2 = string
/**
 * @maxItems 50
 */
export type EngineeringCases = ProductEngineeringCase[]
/**
 * @maxItems 30
 */
export type Interfaces1 = string[]
/**
 * @maxItems 50
 */
export type Limitations2 = string[]
export type LowAltitudeNotice = '产品发布不代表空域、适航、飞手和项目许可。' | null
export type Id5 = string
export type Name2 = string
export type ProcurementNotice = '仅供技术调研，不构成采购建议'
export type ProductKind4 = string
export type Attribution1 = string
export type ClaimId1 = string
/**
 * @minItems 1
 */
export type EvidenceIds4 = string[]
export type IndependentEvidenceIds1 = string[]
export type ProductCapabilityKind = 'PROMOTIONAL_CLAIM' | 'VERIFIED_CAPABILITY'
export type Statement1 = string
export type PromotionalClaims = ProductCapability[]
export type VerifiedCapabilities = ProductCapability[]
/**
 * @maxItems 100
 */
export type VersionHistory = string[]

export interface ItemDetail {
  claims?: Claims
  digital_case?: DigitalCaseDetail | null
  evidence?: Evidence
  item: ItemSummary
  notice?: FeedNotice | null
  paper?: PaperDetail | null
  technology_product?: TechnologyProductDetail | null
}
export interface ClaimView {
  claim_type: ClaimType
  decision_status?: DecisionStatus
  evidence_ids: EvidenceIds
  id: Id
  label: Label
  value: Value
}
export interface DigitalCaseDetail {
  ai_short_comment?: AiShortComment
  applicability: Applicability
  application_scenarios: ApplicationScenarios
  claimed_outcomes: ClaimedOutcomes
  deployment_scale?: DeploymentScale
  engineering_domains: EngineeringDomains
  entities: Entities
  lifecycle_stages: LifecycleStages
  limitations: Limitations
  maturity_level: MaturityLevel
  recommended_actions: RecommendedActions
  replication_conditions: ReplicationConditions
  risks: Risks
  technology_tags: TechnologyTags
  verified_outcomes: VerifiedOutcomes
}
export interface DigitalCaseOutcome {
  attribution: Attribution
  evidence_ids: EvidenceIds1
  id: Id1
  independent_evidence_ids?: IndependentEvidenceIds
  metric_name?: MetricName
  numeric_value?: NumericValue
  statement: Statement
  unit?: Unit
  verification: OutcomeVerification
}
export interface DigitalCaseEntity {
  claim_id: ClaimId
  entity_type: DigitalCaseEntityType
  id: Id2
  name: Name
  relation_type: RelationType
}
export interface EvidenceView {
  char_end?: CharEnd
  char_start?: CharStart
  claim_ids: ClaimIds
  document_version_id?: DocumentVersionId
  excerpt: Excerpt
  excerpt_sha256: ExcerptSha256
  id: Id3
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
  id: Id4
  is_saved?: IsSaved
  last_updated_at?: LastUpdatedAt
  one_sentence_fact?: OneSentenceFact
  original_url: OriginalUrl1
  publication_revision_id: PublicationRevisionId
  publication_status?: PublicationStatus | null
  relevance_reason?: RelevanceReason
  review_status: ReviewStatus
  scores?: ScoreSummary | null
  source_name: SourceName
  source_published_at: SourcePublishedAt
  source_role?: SourceRole
  tags?: Tags
  title: Title
  type_summary?: TypeSummary
}
export interface ScoreSummary {
  authority?: ScoreDimensionSummary | null
  confidence?: ScoreDimensionSummary | null
  evidence?: ScoreDimensionSummary | null
  heat?: ScoreDimensionSummary | null
  impact?: ScoreDimensionSummary | null
  novelty?: ScoreDimensionSummary | null
  relevance?: ScoreDimensionSummary | null
  timeliness?: ScoreDimensionSummary | null
}
export interface ScoreDimensionSummary {
  calculated_at: CalculatedAt
  dimension: ScoreDimension
  features: Features
  overridden?: Overridden
  override_reason?: OverrideReason
  raw_score: RawScore
  rule_version: RuleVersion
  score: Score
}
export interface ScoreFeature {
  code: Code
  explanation: Explanation
  label: Label1
  points: Points
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
export interface DigitalCaseTypeSummary {
  ai_short_comment?: AiShortComment1
  application_scenarios: ApplicationScenarios1
  deployment_scale?: DeploymentScale1
  kind: Kind2
  maturity_level: MaturityLevel
  publisher_claim_label?: PublisherClaimLabel
  relevance: RelevanceSummary
  source_nature: DigitalCaseSourceNature
  srbg_relationship: SrbgRelationship
}
export interface RelevanceSummary {
  factors: Factors
  rule_version: RuleVersion1
  score: Score1
}
export interface RelevanceFactor {
  code: Code1
  label: Label2
  points: Points1
}
export interface PaperTypeSummary {
  access_level: PaperAccessLevel
  ai_short_comment?: AiShortComment2
  doi?: Doi
  engineering_domains: EngineeringDomains1
  journal?: Journal
  kind: Kind3
  maturity_level: MaturityLevel
  open_status: PaperOpenStatus
  paper_type: PaperType
  relation_status: PaperRelationStatus
  technology_tags: TechnologyTags1
  year?: Year
}
export interface SoftwareProductTypeSummary {
  deployment_modes: DeploymentModes
  evidence_level: ProductEvidenceLevel
  interfaces: Interfaces
  kind: Kind4
  model_no?: ModelNo
  product_kind: ProductKind
  product_name: ProductName
  promotional_claim_count: PromotionalClaimCount
  vendor_name: VendorName
  verified_capability_count: VerifiedCapabilityCount
  version?: Version
}
export interface IotProductTypeSummary {
  connectivity: Connectivity
  evidence_level: ProductEvidenceLevel
  kind: Kind5
  maturity_level: MaturityLevel
  model_no?: ModelNo1
  product_kind: ProductKind1
  product_name: ProductName1
  promotional_claim_count: PromotionalClaimCount1
  vendor_name: VendorName1
  verified_capability_count: VerifiedCapabilityCount1
  version?: Version1
}
export interface LowAltitudeEquipmentTypeSummary {
  evidence_level: ProductEvidenceLevel
  kind: Kind6
  model_no?: ModelNo2
  payload_types: PayloadTypes
  permit_status: ProductPermitStatus
  platform_type?: PlatformType
  product_kind: ProductKind2
  product_name: ProductName2
  promotional_claim_count: PromotionalClaimCount2
  vendor_name: VendorName2
  verified_capability_count: VerifiedCapabilityCount2
  version?: Version2
}
export interface AiEquipmentTypeSummary {
  ai_tasks: AiTasks
  equipment_form?: EquipmentForm
  evidence_level: ProductEvidenceLevel
  kind: Kind7
  maturity_level: MaturityLevel
  model_no?: ModelNo3
  product_kind: ProductKind3
  product_name: ProductName3
  production_validation: ProductionValidation
  promotional_claim_count: PromotionalClaimCount3
  vendor_name: VendorName3
  verified_capability_count: VerifiedCapabilityCount3
  version?: Version3
}
export interface FeedNotice {
  code: Code2
  level: Level
  message: Message
}
export interface PaperDetail {
  abstract?: Abstract
  abstract_availability: AbstractAvailability
  access_level: PaperAccessLevel
  authors: Authors
  doi?: Doi1
  engineering_domains: EngineeringDomains2
  issns: Issns
  issue?: Issue
  journal?: Journal1
  keywords: Keywords
  maturity_level: MaturityLevel
  open_fulltext_url?: OpenFulltextUrl
  open_status: PaperOpenStatus
  pages?: Pages
  relation_status: PaperRelationStatus
  research_interpretation?: ResearchInterpretation | null
  similar_papers: SimilarPapers
  technology_tags: TechnologyTags2
  volume?: Volume
  year?: Year2
}
export interface PaperAuthor {
  institutions: Institutions
  name: Name1
  orcid?: Orcid
}
export interface ResearchInterpretation {
  claim_ids: ClaimIds1
  conclusions: Conclusions
  conditions: Conditions
  evidence_ids: EvidenceIds2
  limitations: Limitations1
  method?: Method
  research_object?: ResearchObject
}
export interface SimilarPaper {
  item_id: ItemId
  journal?: Journal2
  match_reasons: MatchReasons
  title: Title1
  year?: Year1
}
export interface TechnologyProductDetail {
  application_scenarios: ApplicationScenarios2
  current_version?: CurrentVersion
  deployment_modes: DeploymentModes1
  engineering_cases: EngineeringCases
  evidence_level: ProductEvidenceLevel
  interfaces: Interfaces1
  limitations: Limitations2
  low_altitude_notice?: LowAltitudeNotice
  model?: ProductEntity | null
  permit_status: ProductPermitStatus
  procurement_notice: ProcurementNotice
  product: ProductEntity
  product_kind: ProductKind4
  promotional_claims: PromotionalClaims
  vendor: ProductEntity
  verified_capabilities: VerifiedCapabilities
  version_history: VersionHistory
}
export interface ProductEngineeringCase {
  evidence_ids: EvidenceIds3
  item_id: ItemId1
  title: Title2
}
export interface ProductEntity {
  id: Id5
  name: Name2
}
export interface ProductCapability {
  attribution: Attribution1
  claim_id: ClaimId1
  evidence_ids: EvidenceIds4
  independent_evidence_ids?: IndependentEvidenceIds1
  kind: ProductCapabilityKind
  statement: Statement1
}
