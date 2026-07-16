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
export type Enabled = boolean
export type FixtureCount = number
export type GovernanceOwnerId = string | null
export type Id = string
export type SourceIndustry =
  'HIGHWAY' | 'BRIDGE' | 'TUNNEL' | 'RAILWAY' | 'RAIL_TRANSIT' | 'GENERAL_TRANSPORT' | 'UNKNOWN'
export type Industries = SourceIndustry[]
export type LanguageTags = string[]
/**
 * Authoritative V2 source lifecycle computed by the server.
 */
export type SourceLifecycleState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'TRIAL' | 'ACTIVE' | 'PAUSED' | 'RETIRED'
export type Name = string
export type Priority = string
export type RegionCodes = string[]
export type RegistryCode = string | null
/**
 * Server-derived execution authorization; never accepted as client input.
 */
export type RuntimeAuthorization = 'DENIED' | 'TRIAL_ONLY' | 'PRODUCTION'
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

export interface SourceSummary {
  authority_level: AuthorityLevel
  available_actions?: AvailableActions
  base_url: BaseUrl
  channel: SourceChannel
  content_domains?: ContentDomains
  country_codes?: CountryCodes
  created_at: CreatedAt
  declared_roles?: DeclaredRoles
  effective_active: EffectiveActive
  enabled: Enabled
  fixture_count: FixtureCount
  governance_owner_id?: GovernanceOwnerId
  id: Id
  industries?: Industries
  language_tags?: LanguageTags
  lifecycle_state: SourceLifecycleState
  name: Name
  priority: Priority
  region_codes?: RegionCodes
  registry_code: RegistryCode
  runtime_authorization: RuntimeAuthorization
  source_type: SourceType
  state: SourceState
}
