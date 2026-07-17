export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2' | 'UNKNOWN'
export type SourceLifecycleAction =
  | 'SUBMIT_COMPLIANCE'
  | 'START_FIXTURE_TRIAL'
  | 'START_LIVE_TRIAL'
  | 'APPROVE_PRODUCTION'
  | 'PAUSE'
  | 'RESUME'
  | 'RETIRE'
export type AvailableActions = SourceLifecycleAction[]
export type BaseUrl = string
export type SourceChannel = 'DIGITAL' | 'SAFETY' | 'BOTH'
export type CollectionMethod = string
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
export type CreatedAt = string
export type CurrentConnectorConfigVersionId = string | null
export type CurrentPolicyVersionId = string | null
export type CurrentTrialRunId = string | null
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
export type EffectiveActive = boolean
export type EffectiveActive1 = boolean
export type FixtureCount = number
export type FixtureSetSha256 = string | null
export type MissingReasons = string[]
export type OnboardingPolicyMatches = boolean
export type OnboardingValid = boolean
export type PolicyValid = boolean
export type RequiredChecksComplete = boolean
export type RequiredFixtureCount = number
export type Enabled = boolean
export type FixtureCount1 = number
export type GovernanceOwnerId = string | null
export type Id = string
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
/**
 * Authoritative V2 source lifecycle computed by the server.
 */
export type SourceLifecycleState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'TRIAL' | 'ACTIVE' | 'PAUSED' | 'RETIRED'
export type Name = string
export type Owner = string
export type PollIntervalMinutes = number
export type Priority = string
export type RegionCodes = string[]
export type RegistryCode = string | null
/**
 * Server-derived execution authorization; never accepted as client input.
 */
export type RuntimeAuthorization = 'DENIED' | 'TRIAL_ONLY' | 'PRODUCTION'
export type AssessedAt = string
/**
 * @maxItems 50
 */
export type EvidenceRefs = string[]
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type RuleVersion = string
export type AssessedAt1 = string
/**
 * @maxItems 50
 */
export type EvidenceRefs1 = string[]
export type SourceIndependenceLevel =
  'EDITORIALLY_INDEPENDENT' | 'PARTIALLY_INDEPENDENT' | 'NOT_INDEPENDENT' | 'UNKNOWN'
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes1 = string[]
export type RuleVersion1 = string
export type SourceType =
  | 'government'
  | 'standards'
  | 'journal'
  | 'research_institute'
  | 'association'
  | 'enterprise'
  | 'media'
  | 'academic_api'
  | 'academic_database'
/**
 * Deprecated V1 source state retained only for compatibility projections.
 */
export type SourceState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'FIXTURE_TEST' | 'APPROVED' | 'ACTIVE'

export interface SourceDetail {
  authority_level: AuthorityLevel
  available_actions?: AvailableActions
  base_url: BaseUrl
  channel: SourceChannel
  collection_method: CollectionMethod
  content_domains?: ContentDomains
  country_codes?: CountryCodes
  created_at: CreatedAt
  current_connector_config_version_id?: CurrentConnectorConfigVersionId
  current_policy_version_id?: CurrentPolicyVersionId
  current_trial_run_id?: CurrentTrialRunId
  declared_roles?: DeclaredRoles
  effective_active: EffectiveActive
  eligibility: SourceEligibility
  enabled: Enabled
  fixture_count: FixtureCount1
  governance_owner_id?: GovernanceOwnerId
  id: Id
  industries?: Industries
  language_tags?: LanguageTags
  lifecycle_state: SourceLifecycleState
  name: Name
  owner: Owner
  poll_interval_minutes: PollIntervalMinutes
  priority: Priority
  region_codes?: RegionCodes
  registry_code: RegistryCode
  runtime_authorization: RuntimeAuthorization
  source_authority?: SourceAuthorityAssessment | null
  source_independence?: SourceIndependenceAssessment | null
  source_type: SourceType
  state: SourceState
}
export interface SourceEligibility {
  effective_active: EffectiveActive1
  fixture_count: FixtureCount
  fixture_set_sha256?: FixtureSetSha256
  missing_reasons: MissingReasons
  onboarding_policy_matches: OnboardingPolicyMatches
  onboarding_valid: OnboardingValid
  policy_valid: PolicyValid
  required_checks_complete: RequiredChecksComplete
  required_fixture_count?: RequiredFixtureCount
}
export interface SourceAuthorityAssessment {
  assessed_at: AssessedAt
  evidence_refs?: EvidenceRefs
  level: AuthorityLevel
  reason_codes: ReasonCodes
  rule_version: RuleVersion
}
export interface SourceIndependenceAssessment {
  assessed_at: AssessedAt1
  evidence_refs?: EvidenceRefs1
  level: SourceIndependenceLevel
  reason_codes: ReasonCodes1
  rule_version: RuleVersion1
}
