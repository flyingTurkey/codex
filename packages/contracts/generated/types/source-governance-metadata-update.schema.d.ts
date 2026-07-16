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
 * @minItems 1
 * @maxItems 30
 */
export type ContentDomains = SourceContentDomain[]
/**
 * @minItems 1
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
 * @minItems 1
 * @maxItems 20
 */
export type DeclaredRoles = SourceDeclaredRole[]
export type GovernanceOwnerId = string
export type SourceIndustry =
  'HIGHWAY' | 'BRIDGE' | 'TUNNEL' | 'RAILWAY' | 'RAIL_TRANSIT' | 'GENERAL_TRANSPORT' | 'UNKNOWN'
/**
 * @minItems 1
 * @maxItems 20
 */
export type Industries = SourceIndustry[]
/**
 * @minItems 1
 * @maxItems 20
 */
export type LanguageTags = string[]
export type Reason = string
/**
 * @minItems 1
 * @maxItems 50
 */
export type RegionCodes = string[]

/**
 * Governance-owned coverage metadata; lifecycle authority is intentionally absent.
 */
export interface SourceGovernanceMetadataUpdate {
  content_domains: ContentDomains
  country_codes: CountryCodes
  declared_roles: DeclaredRoles
  governance_owner_id: GovernanceOwnerId
  industries: Industries
  language_tags: LanguageTags
  reason: Reason
  region_codes: RegionCodes
}
