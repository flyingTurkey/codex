export type Confidence = number
/**
 * @minItems 1
 * @maxItems 10
 */
export type EvidenceIds = string[]
export type ReasonCode = string
export type Value = string
/**
 * @maxItems 30
 */
export type ContentDomainCandidates = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type CountryCandidates = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type DeclaredRoleCandidates = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type IndustryCandidates = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type LanguageCandidates = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type OrganizationClues = SourceProfileCandidate[]
/**
 * @maxItems 20
 */
export type OwnershipClues = SourceProfileCandidate[]
/**
 * @maxItems 50
 */
export type RegionCandidates = SourceProfileCandidate[]

/**
 * Semantic clues only; authority and independence remain server-derived.
 */
export interface SourceProfileModelOutput {
  content_domain_candidates: ContentDomainCandidates
  country_candidates: CountryCandidates
  declared_role_candidates: DeclaredRoleCandidates
  industry_candidates: IndustryCandidates
  language_candidates: LanguageCandidates
  organization_clues: OrganizationClues
  ownership_clues: OwnershipClues
  region_candidates: RegionCandidates
}
export interface SourceProfileCandidate {
  confidence: Confidence
  evidence_ids: EvidenceIds
  reason_code: ReasonCode
  value: Value
}
