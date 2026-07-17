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
/**
 * @maxItems 30
 */
export type Industries = SourceIndustry[]
/**
 * @maxItems 20
 */
export type LanguageTags = string[]
export type Reason = string
export type Url = string

/**
 * Discovery input; lifecycle status and qualification facts remain server-owned.
 */
export interface SourceCandidateCreateRequest {
  content_domains?: ContentDomains
  industries?: Industries
  language_tags?: LanguageTags
  reason: Reason
  url: Url
}
