export type CanonicalEventId = string | null
export type ClaimId = string
/**
 * @minItems 1
 * @maxItems 100
 */
export type EvidenceIds = string[]
export type FieldName = string
export type Value = string
/**
 * @maxItems 500
 */
export type Claims = PublishedClaimV1[]
export type ClaimId1 = string
/**
 * @minItems 1
 */
export type EvidenceIds1 = string[]
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
export type Value1 = string | number | string[]
export type ConfirmedFacts = ConfirmedFact[]
export type DocumentId = string
export type OriginalUrl = string
/**
 * @maxItems 1000
 */
export type PublicationRevisionIds = string[]
export type SourceName = string
export type SourceLineageRole = 'ORIGINAL' | 'REPRINT' | 'MIRROR' | 'INDEPENDENT_REPORT'
export type SourceRolePending = boolean
/**
 * @maxItems 500
 */
export type Documents = PublishedDocumentReferenceV1[]
export type EngineeringType = string | null
export type EventStatus = 'ACTIVE' | 'MERGED' | 'SPLIT' | 'WITHDRAWN'
export type EventType =
  'SAFETY_INCIDENT' | 'REGULATION_CHANGE' | 'DIGITAL_PROJECT' | 'RESEARCH_RESULT' | 'PRODUCT_RELEASE'
export type EventVersion = number
export type ContentSha256 = string
export type EvidenceId = string
export type Locator = string
/**
 * @maxItems 500
 */
export type Evidence = PublishedEvidenceReferenceV1[]
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
export type IndependentSourceCount = number
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
export type SimilarScenarioTag =
  | 'HIGHWAY_OPERATION_GEOLOGICAL_RISK'
  | 'ROADBED_SLOPE_INSTABILITY'
  | 'BRIDGE_APPROACH_TRANSITION'
  | 'EXTREME_WEATHER_EXPOSURE'
  | 'TEMPORARY_STRUCTURE_FAILURE'
  | 'TUNNEL_GEOLOGICAL_RISK'
export type SimilarScenarioTags = SimilarScenarioTag[]
/**
 * @maxItems 500
 */
export type SourceComparison = PublishedDocumentReferenceV1[]
export type SplitChildEventIds = string[]
export type CanonicalEventId1 = string | null
/**
 * Subject-matter severity, independent from publication handling risk.
 */
export type ContentSeverity = 'UNASSESSED' | 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
export type ItemType =
  | 'DIGITAL_CASE'
  | 'JOURNAL_PAPER'
  | 'SOFTWARE_PRODUCT'
  | 'IOT_PRODUCT'
  | 'LOW_ALTITUDE_EQUIPMENT'
  | 'AI_EQUIPMENT'
  | 'SAFETY_REGULATION'
  | 'SAFETY_CASE'
export type DiscoveryStatus = 'MACHINE_DISCOVERED' | 'HUMAN_CURATED'
export type Channel = 'DIGITAL' | 'SAFETY'
export type EventRevisionId = string | null
export type EventStatus1 = 'ACTIVE' | 'MERGED' | 'SPLIT' | 'WITHDRAWN'
export type EventVersion1 = number
export type FactReviewStatus = 'PENDING_HUMAN_REVIEW' | 'HUMAN_REVIEWED'
export type FirstDiscoveredAt = string
export type Generation = number
export type Id2 = string
export type OneSentenceFact = string | null
export type OriginalUrl1 = string
/**
 * Maximum content projection level decided by server-side policy.
 */
export type ProjectionLevel = 'NONE' | 'METADATA_ONLY' | 'FULL'
export type ProjectionVersion = '1.0.0' | '1.1.0'
export type PublicationRevisionId = string | null
/**
 * @maxItems 1000
 */
export type PublicationRevisionIds1 = string[]
/**
 * Publication handling risk; it never grants content visibility.
 */
export type PublicationRiskTier = 'R1' | 'R2' | 'R3' | 'R4'
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SourceName1 = string
export type SourcePublishedAt = string | null
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
export type EngineeringType1 = string | null
export type EventId1 = string | null
export type HazardType1 = string | null
export type Injuries = number | null
export type Kind1 = 'SAFETY_CASE'
export type LossAmountMinor = number | null
export type LossCurrency = string | null
export type OccurredAt1 = string | null
/**
 * null means no formal investigation basis; an empty list means formal evidence was reviewed and stated no direct-cause finding
 */
export type OfficialDirectCauses = string[] | null
export type PreventionMeasureTags1 = PreventionMeasureTag[] | null
/**
 * Reviewed rectification evaluation result; null means not established
 */
export type RectificationHasOpenIssues1 = boolean | null
export type Region1 = string | null
export type SafetyCaseReportStage =
  'INITIAL_REPORT' | 'FOLLOW_UP_REPORT' | 'FINAL_INVESTIGATION' | 'ENFORCEMENT' | 'RECTIFICATION'
/**
 * null means no formal investigation or enforcement basis; an empty list means formal evidence was reviewed and stated no responsibility finding
 */
export type ResponsibilityFindings = string[] | null
export type SimilarScenarioTags1 = SimilarScenarioTag[] | null
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
export type EventId2 = string
export type DocumentStates = DocumentState[] | null
export type DocumentState = 'UPDATED' | 'RE_REVIEW_PENDING' | 'WITHDRAWN' | 'SOURCE_UNAVAILABLE'
export type EvidenceCount = number | null
export type ItemId = string
export type OriginalUrl2 = string
export type PublicationRevisionId1 = string | null
export type SourceName2 = string
export type SourcePublishedAt1 = string | null
export type Title1 = string
export type Items = EventItem[]
export type Title2 = string
export type TopicIds = string[]
export type TypeDetail =
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
export type ClaimId2 = string | null
export type ConflictId = string | null
export type DisplayValue = '待核实'
export type EvidenceIds2 = string[]
export type Label3 = string
export type Reason = string
export type SourceItemId1 = string
export type Status1 = 'PENDING_REVIEW' | 'CONFLICTING'
export type Value2 = null
export type UnverifiedFacts = UnverifiedFact[]

export interface EventDetail {
  canonical_event_id?: CanonicalEventId
  claims?: Claims
  confirmed_facts: ConfirmedFacts
  documents?: Documents
  engineering_type?: EngineeringType
  event_status?: EventStatus
  event_type: EventType
  event_version?: EventVersion
  evidence?: Evidence
  hazard_type?: HazardType
  id: Id
  incident_status?: IncidentStatus | null
  independent_source_count?: IndependentSourceCount
  occurred_at?: OccurredAt
  prevention_measure_tags: PreventionMeasureTags
  project_name?: ProjectName
  rectification_has_open_issues?: RectificationHasOpenIssues
  region?: Region
  relations: Relations
  scores?: ScoreSummary | null
  similar_scenario_tags: SimilarScenarioTags
  source_comparison?: SourceComparison
  split_child_event_ids?: SplitChildEventIds
  summary?: PublishedEventSummaryV1 | null
  timeline: EventTimeline
  title: Title2
  topic_ids?: TopicIds
  type_detail?: TypeDetail
  unverified_facts: UnverifiedFacts
}
export interface PublishedClaimV1 {
  claim_id: ClaimId
  evidence_ids: EvidenceIds
  field_name: FieldName
  value: Value
}
export interface ConfirmedFact {
  claim_id: ClaimId1
  evidence_ids: EvidenceIds1
  field: SafetyCaseFactField
  label: Label
  reviewed_at: ReviewedAt
  source_item_id: SourceItemId
  status?: Status
  unit?: Unit
  value: Value1
}
export interface PublishedDocumentReferenceV1 {
  document_id: DocumentId
  original_url: OriginalUrl
  publication_revision_ids?: PublicationRevisionIds
  source_name: SourceName
  source_role?: SourceLineageRole | null
  source_role_pending?: SourceRolePending
}
export interface PublishedEvidenceReferenceV1 {
  content_sha256: ContentSha256
  evidence_id: EvidenceId
  locator: Locator
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
/**
 * Versioned, event-keyed content projection for internal readers.
 */
export interface PublishedEventSummaryV1 {
  canonical_event_id?: CanonicalEventId1
  content_severity: ContentSeverity
  content_type: ItemType
  discovery_status: DiscoveryStatus
  domain: Channel
  event_revision_id?: EventRevisionId
  event_status?: EventStatus1
  event_type?: EventType | null
  event_version?: EventVersion1
  fact_review_status: FactReviewStatus
  first_discovered_at: FirstDiscoveredAt
  generation: Generation
  id: Id2
  one_sentence_fact?: OneSentenceFact
  original_url: OriginalUrl1
  projection_level: ProjectionLevel
  projection_version: ProjectionVersion
  publication_revision_id: PublicationRevisionId
  publication_revision_ids?: PublicationRevisionIds1
  publication_risk_tier: PublicationRiskTier
  review_status: ReviewStatus
  source_name: SourceName1
  source_published_at: SourcePublishedAt
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
  engineering_type?: EngineeringType1
  event_id?: EventId1
  hazard_type?: HazardType1
  incident_status?: IncidentStatus | null
  injuries?: Injuries
  kind: Kind1
  loss_amount_minor?: LossAmountMinor
  loss_currency?: LossCurrency
  occurred_at?: OccurredAt1
  official_direct_causes?: OfficialDirectCauses
  prevention_measure_tags?: PreventionMeasureTags1
  rectification_has_open_issues?: RectificationHasOpenIssues1
  region?: Region1
  report_stage?: SafetyCaseReportStage | null
  responsibility_findings?: ResponsibilityFindings
  similar_scenario_tags?: SimilarScenarioTags1
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
export interface EventTimeline {
  event_id: EventId2
  items: Items
}
export interface EventItem {
  document_states?: DocumentStates
  evidence_count?: EvidenceCount
  incident_status?: IncidentStatus | null
  item_id: ItemId
  original_url: OriginalUrl2
  publication_revision_id: PublicationRevisionId1
  relation_type?: EventRelation | null
  report_stage?: SafetyCaseReportStage | null
  review_status: ReviewStatus
  source_name: SourceName2
  source_published_at: SourcePublishedAt1
  title: Title1
}
/**
 * Public-safe unresolved fact: candidate values are intentionally absent.
 */
export interface UnverifiedFact {
  claim_id?: ClaimId2
  conflict_id?: ConflictId
  display_value?: DisplayValue
  evidence_ids?: EvidenceIds2
  field: SafetyCaseFactField
  label: Label3
  reason: Reason
  source_item_id: SourceItemId1
  status: Status1
  value?: Value2
}
