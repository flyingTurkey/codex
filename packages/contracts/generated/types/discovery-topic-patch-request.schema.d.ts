export type Enabled = boolean | null
export type ExcludedTerms = string[] | null
export type FocusRegions = string[] | null
export type Keywords = string[] | null

export interface DiscoveryTopicPatchRequest {
  enabled?: Enabled
  excluded_terms?: ExcludedTerms
  focus_regions?: FocusRegions
  keywords?: Keywords
}
