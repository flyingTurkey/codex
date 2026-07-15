export type Fingerprint = string
export type Freshness = 'fresh' | 'delayed' | 'partial'
export type GeneratedAt = string
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
export type Id = string
export type IsSaved = boolean | null
export type LastUpdatedAt = string | null
export type OneSentenceFact = string | null
export type OriginalUrl = string
export type PublicationRevisionId = string | null
export type PublicationStatus = 'PENDING_REVIEW' | 'PUBLISHED' | 'WITHDRAWN'
export type RelevanceReason = string | null
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
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
export type AiShortComment = null
/**
 * @maxItems 20
 */
export type ApplicationScenarios = string[]
export type DeploymentScale = string | null
export type Kind2 = 'DIGITAL_CASE'
export type MaturityLevel =
  | 'CONCEPT'
  | 'LAB_PROTOTYPE'
  | 'ENGINEERING_PROTOTYPE'
  | 'PILOT'
  | 'SINGLE_PROJECT_PRODUCTION'
  | 'MULTI_PROJECT_REPLICATION'
  | 'ENTERPRISE_SCALE'
  | 'UNKNOWN'
export type PublisherClaimLabel = string | null
export type Code = 'ENGINEERING_DOMAIN' | 'SICHUAN' | 'SRBG_DIRECT'
export type Label = string
export type Points = number
/**
 * @minItems 1
 * @maxItems 3
 */
export type Factors = RelevanceFactor[]
export type RuleVersion = 'relevance-v1.0.0'
export type Score = number
export type DigitalCaseSourceNature = 'GOVERNMENT_CASE_COLLECTION' | 'ENTERPRISE_SELF_REPORT'
export type SrbgRelationship = string
export type PaperAccessLevel = 'METADATA_ONLY' | 'ABSTRACT_ALLOWED' | 'OPEN_FULLTEXT'
export type AiShortComment1 = null
export type Doi = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains = string[]
export type Journal = string | null
export type Kind3 = 'JOURNAL_PAPER'
export type PaperOpenStatus = 'OPEN' | 'CLOSED' | 'UNKNOWN'
export type PaperType = 'ARTICLE' | 'REVIEW' | 'METHOD' | 'CASE_STUDY' | 'OTHER' | 'UNKNOWN'
export type PaperRelationStatus = 'CURRENT' | 'CORRECTED' | 'RETRACTED' | 'WITHDRAWN'
/**
 * @maxItems 50
 */
export type TechnologyTags = string[]
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
export type Items = ItemSummary[]
export type NextCursor = string | null
export type Code1 = string
export type Level = 'info' | 'warning' | 'error'
export type Message = string
export type Notices = FeedNotice[]

export interface FeedPage {
  fingerprint: Fingerprint
  freshness: Freshness
  generated_at: GeneratedAt
  items: Items
  next_cursor: NextCursor
  notices: Notices
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
  id: Id
  is_saved?: IsSaved
  last_updated_at?: LastUpdatedAt
  one_sentence_fact?: OneSentenceFact
  original_url: OriginalUrl
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
export interface DigitalCaseTypeSummary {
  ai_short_comment?: AiShortComment
  application_scenarios: ApplicationScenarios
  deployment_scale?: DeploymentScale
  kind: Kind2
  maturity_level: MaturityLevel
  publisher_claim_label?: PublisherClaimLabel
  relevance: RelevanceSummary
  source_nature: DigitalCaseSourceNature
  srbg_relationship: SrbgRelationship
}
export interface RelevanceSummary {
  factors: Factors
  rule_version: RuleVersion
  score: Score
}
export interface RelevanceFactor {
  code: Code
  label: Label
  points: Points
}
export interface PaperTypeSummary {
  access_level: PaperAccessLevel
  ai_short_comment?: AiShortComment1
  doi?: Doi
  engineering_domains: EngineeringDomains
  journal?: Journal
  kind: Kind3
  maturity_level: MaturityLevel
  open_status: PaperOpenStatus
  paper_type: PaperType
  relation_status: PaperRelationStatus
  technology_tags: TechnologyTags
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
  code: Code1
  level: Level
  message: Message
}
