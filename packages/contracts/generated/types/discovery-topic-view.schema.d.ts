export type Code = 'HIGHWAY' | 'BRIDGE' | 'TUNNEL' | 'RAIL' | 'DIGITAL' | 'AI_IOT_LOW_ALTITUDE' | 'SAFETY'
export type Enabled = boolean
/**
 * @maxItems 50
 */
export type ExcludedTerms = string[]
/**
 * @maxItems 50
 */
export type FocusRegions = string[]
export type Id = string
/**
 * @minItems 1
 * @maxItems 50
 */
export type Keywords = string[]
export type Name = string
export type UpdatedAt = string
export type Version = number

export interface DiscoveryTopicView {
  code: Code
  enabled: Enabled
  excluded_terms: ExcludedTerms
  focus_regions: FocusRegions
  id: Id
  keywords: Keywords
  name: Name
  updated_at: UpdatedAt
  version: Version
}
