export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2' | 'UNKNOWN'
export type ContentDomains = SourceContentDomain[] | null
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
export type CountryCodes = string[] | null
export type DeclaredRoles = SourceDeclaredRole[] | null
export type SourceDeclaredRole =
  | 'OFFICIAL_PRIMARY'
  | 'OFFICIAL_SECONDARY'
  | 'STANDARDS_PUBLISHER'
  | 'RESEARCH_PUBLISHER'
  | 'MANUFACTURER'
  | 'INDEPENDENT_REPORTER'
  | 'AGGREGATOR'
  | 'UNKNOWN'
export type SourceIndependenceLevel =
  'EDITORIALLY_INDEPENDENT' | 'PARTIALLY_INDEPENDENT' | 'NOT_INDEPENDENT' | 'UNKNOWN'
export type Industries = SourceIndustry[] | null
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
export type LanguageTags = string[] | null
export type RegionCodes = string[] | null

export interface SourceProfileOverrideRequest {
  authority_level?: AuthorityLevel | null
  content_domains?: ContentDomains
  country_codes?: CountryCodes
  declared_roles?: DeclaredRoles
  independence_level?: SourceIndependenceLevel | null
  industries?: Industries
  language_tags?: LanguageTags
  region_codes?: RegionCodes
}
