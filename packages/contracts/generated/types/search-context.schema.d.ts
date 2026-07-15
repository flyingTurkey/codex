export type MatchKind = 'EXACT_IDENTIFIER' | 'TITLE_ENTITY_TAG' | 'BODY' | 'SEMANTIC'
/**
 * @maxItems 10
 */
export type MatchedFields = string[]
/**
 * @maxItems 10
 */
export type MatchedIdentifiers = string[]
export type SemanticStatus = 'DISABLED' | 'ENABLED' | 'DEGRADED'

export interface SearchContext {
  match_kind: MatchKind
  matched_fields?: MatchedFields
  matched_identifiers?: MatchedIdentifiers
  semantic_status: SemanticStatus
}
