export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2' | 'UNKNOWN'
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
/**
 * @maxItems 30
 */
export type ContentDomains = SourceContentDomain[]
/**
 * @maxItems 20
 */
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
/**
 * @maxItems 20
 */
export type DeclaredRoles = SourceDeclaredRole[]
export type GovernanceOwnerId = string | null
export type SourceIndustry =
  'HIGHWAY' | 'BRIDGE' | 'TUNNEL' | 'RAILWAY' | 'RAIL_TRANSIT' | 'GENERAL_TRANSPORT' | 'UNKNOWN'
/**
 * @maxItems 20
 */
export type Industries = SourceIndustry[]
/**
 * @maxItems 20
 */
export type LanguageTags = string[]
export type Name = string
export type Owner = string
export type PollIntervalMinutes = number
export type Priority = 'P0' | 'P1' | 'P2'
/**
 * @maxItems 50
 */
export type RegionCodes = string[]
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

export interface CreateSourceRequest {
  authority_level: AuthorityLevel
  base_url: BaseUrl
  channel: SourceChannel
  collection_method: CollectionMethod
  content_domains?: ContentDomains
  country_codes?: CountryCodes
  declared_roles?: DeclaredRoles
  governance_owner_id?: GovernanceOwnerId
  industries?: Industries
  language_tags?: LanguageTags
  name: Name
  owner: Owner
  poll_interval_minutes: PollIntervalMinutes
  priority: Priority
  region_codes?: RegionCodes
  source_type: SourceType
}
