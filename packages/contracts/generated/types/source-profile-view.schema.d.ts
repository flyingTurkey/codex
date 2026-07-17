export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2' | 'UNKNOWN'
export type SourceContentDomain =
  | 'DIGITAL_TRANSFORMATION_CASE'
  | 'RESEARCH_PAPER'
  | 'SOFTWARE_PLATFORM'
  | 'IOT_EQUIPMENT'
  | 'LOW_ALTITUDE_EQUIPMENT'
  | 'AI_APPLICATION'
  | 'SAFETY_REGULATION'
  | 'STANDARD_GUIDANCE'
  | 'ACCIDENT_INVESTIGATION'
  | 'OFFICIAL_NOTICE'
  | 'PENALTY'
  | 'RECTIFICATION'
  | 'UNKNOWN'
export type ContentDomains = SourceContentDomain[]
export type CountryCodes = string[]
export type SourceDeclaredRole =
  | 'OFFICIAL_PRIMARY'
  | 'OFFICIAL_SECONDARY'
  | 'STANDARDS_PUBLISHER'
  | 'RESEARCH_PUBLISHER'
  | 'MANUFACTURER'
  | 'INDEPENDENT_REPORTER'
  | 'AGGREGATOR'
  | 'UNKNOWN'
export type DeclaredRoles = SourceDeclaredRole[]
export type SourceIndependenceLevel =
  'EDITORIALLY_INDEPENDENT' | 'PARTIALLY_INDEPENDENT' | 'NOT_INDEPENDENT' | 'UNKNOWN'
export type SourceIndustry =
  | 'HIGHWAY'
  | 'BRIDGE'
  | 'TUNNEL'
  | 'RAILWAY'
  | 'RAIL_TRANSIT'
  | 'WATER_CONSERVANCY'
  | 'MUNICIPAL'
  | 'BUILDING'
  | 'ENERGY'
  | 'PORT_WATERWAY'
  | 'AIRPORT'
  | 'GENERAL_TRANSPORT'
  | 'UNKNOWN'
export type Industries = SourceIndustry[]
export type LanguageTags = string[]
export type RegionCodes = string[]
export type EvidenceId = string
export type Excerpt = string
export type Kind = string
export type Sha256 = string
export type Url = string
/**
 * @maxItems 50
 */
export type Evidence = SourceProfileEvidenceView[]
export type SourceProfileBasis = 'AUTO_INFERRED' | 'PERSONAL_OVERRIDE'
export type Confidence = number
/**
 * @maxItems 50
 */
export type EvidenceIds = string[]
/**
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type GeneratedAt = string
export type InputSha256 = string
export type ModelVersion = string
export type OverallConfidence = number
/**
 * @maxItems 8
 */
export type OverriddenFields = string[]
export type PromptVersion = string
/**
 * @maxItems 50
 */
export type ReasonCodes1 = string[]
export type RuleVersion = string
export type SchemaVersion = string
export type SnapshotId = string
export type SourceProfileStatus = 'COMPLETE' | 'PARTIAL'
/**
 * @maxItems 20
 */
export type TechnicalFacts = string[]
export type Version = number

export interface SourceProfileView {
  automatic: SourceProfileValues
  effective: SourceProfileValues
  evidence: Evidence
  field_explanations: FieldExplanations
  generated_at: GeneratedAt
  input_sha256: InputSha256
  model_version: ModelVersion
  overall_confidence: OverallConfidence
  overridden_fields?: OverriddenFields
  prompt_version: PromptVersion
  reason_codes: ReasonCodes1
  rule_version: RuleVersion
  schema_version: SchemaVersion
  snapshot_id: SnapshotId
  status: SourceProfileStatus
  technical_facts: TechnicalFacts
  version: Version
}
export interface SourceProfileValues {
  authority_level: AuthorityLevel
  content_domains: ContentDomains
  country_codes: CountryCodes
  declared_roles: DeclaredRoles
  independence_level: SourceIndependenceLevel
  industries: Industries
  language_tags: LanguageTags
  region_codes: RegionCodes
}
export interface SourceProfileEvidenceView {
  evidence_id: EvidenceId
  excerpt: Excerpt
  kind: Kind
  sha256: Sha256
  url: Url
}
export interface FieldExplanations {
  [k: string]: SourceProfileFieldExplanation
}
export interface SourceProfileFieldExplanation {
  basis?: SourceProfileBasis
  confidence: Confidence
  evidence_ids: EvidenceIds
  reason_codes: ReasonCodes
}
