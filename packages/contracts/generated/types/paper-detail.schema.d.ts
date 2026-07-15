export type Abstract = string | null
export type AbstractAvailability = 'AVAILABLE' | 'NOT_PROVIDED' | 'LICENCE_UNCLEAR'
export type PaperAccessLevel = 'METADATA_ONLY' | 'ABSTRACT_ALLOWED' | 'OPEN_FULLTEXT'
/**
 * @maxItems 30
 */
export type Institutions = string[]
export type Name = string
export type Orcid = string | null
/**
 * @maxItems 500
 */
export type Authors = PaperAuthor[]
export type Doi = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains = string[]
/**
 * @maxItems 20
 */
export type Issns = string[]
export type Issue = string | null
export type Journal = string | null
/**
 * @maxItems 100
 */
export type Keywords = string[]
export type MaturityLevel =
  | 'CONCEPT'
  | 'LAB_PROTOTYPE'
  | 'ENGINEERING_PROTOTYPE'
  | 'PILOT'
  | 'SINGLE_PROJECT_PRODUCTION'
  | 'MULTI_PROJECT_REPLICATION'
  | 'ENTERPRISE_SCALE'
  | 'UNKNOWN'
export type OpenFulltextUrl = string | null
export type PaperOpenStatus = 'OPEN' | 'CLOSED' | 'UNKNOWN'
export type Pages = string | null
export type PaperRelationStatus = 'CURRENT' | 'CORRECTED' | 'RETRACTED' | 'WITHDRAWN'
/**
 * @minItems 1
 */
export type ClaimIds = string[]
/**
 * @maxItems 30
 */
export type Conclusions = string[]
/**
 * @maxItems 30
 */
export type Conditions = string[]
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
/**
 * @maxItems 30
 */
export type Limitations = string[]
export type Method = string | null
export type ResearchObject = string | null
export type ItemId = string
export type Journal1 = string | null
/**
 * @minItems 1
 * @maxItems 20
 */
export type MatchReasons = string[]
export type Title = string
export type Year = number | null
/**
 * @maxItems 5
 */
export type SimilarPapers = SimilarPaper[]
/**
 * @maxItems 50
 */
export type TechnologyTags = string[]
export type Volume = string | null
export type Year1 = number | null

export interface PaperDetail {
  abstract?: Abstract
  abstract_availability: AbstractAvailability
  access_level: PaperAccessLevel
  authors: Authors
  doi?: Doi
  engineering_domains: EngineeringDomains
  issns: Issns
  issue?: Issue
  journal?: Journal
  keywords: Keywords
  maturity_level: MaturityLevel
  open_fulltext_url?: OpenFulltextUrl
  open_status: PaperOpenStatus
  pages?: Pages
  relation_status: PaperRelationStatus
  research_interpretation?: ResearchInterpretation | null
  similar_papers: SimilarPapers
  technology_tags: TechnologyTags
  volume?: Volume
  year?: Year1
}
export interface PaperAuthor {
  institutions: Institutions
  name: Name
  orcid?: Orcid
}
export interface ResearchInterpretation {
  claim_ids: ClaimIds
  conclusions: Conclusions
  conditions: Conditions
  evidence_ids: EvidenceIds
  limitations: Limitations
  method?: Method
  research_object?: ResearchObject
}
export interface SimilarPaper {
  item_id: ItemId
  journal?: Journal1
  match_reasons: MatchReasons
  title: Title
  year?: Year
}
