/**
 * @maxItems 20
 */
export type AmbiguityIndicators = string[]
export type Confidence = number
export type ContentForm =
  | 'AUTHORITY_NOTICE'
  | 'PROJECT_RECORD'
  | 'RESEARCH'
  | 'PRODUCT'
  | 'ACCIDENT_UPDATE'
  | 'STANDARD_GUIDANCE'
  | 'OPERATION_UPDATE'
  | 'OTHER'
export type CoreNewFact = string | null
export type DirectRelevance = 'RELEVANT' | 'IRRELEVANT' | 'AMBIGUOUS' | 'FAILED'
export type EngineeringObject =
  | 'HIGHWAY'
  | 'RAILWAY'
  | 'BRIDGE'
  | 'TUNNEL'
  | 'BUILDING'
  | 'MINING'
  | 'MUNICIPAL'
  | 'WATER_CONSERVANCY'
  | 'PORT_WATERWAY'
  | 'AIRPORT'
  | 'ENERGY'
/**
 * @maxItems 11
 */
export type EngineeringObjects = EngineeringObject[]
export type EquipmentFacet = 'CONSTRUCTION_MACHINERY'
/**
 * @maxItems 1
 */
export type EquipmentDomains = EquipmentFacet[]
/**
 * @maxItems 100
 */
export type EvidenceLocators = string[]
export type PrimaryIntelligenceType = 'DIGITAL_TRANSFORMATION' | 'SAFETY_INTELLIGENCE' | 'INDUSTRY_UPDATE'
/**
 * @maxItems 20
 */
export type SecuritySignals = string[]
export type SpecialtyFacet = 'TUNNEL_GAS_MONITORING'
/**
 * @maxItems 1
 */
export type SpecialtyFacets = SpecialtyFacet[]

/**
 * Strict model output; publication and safety authority remain server-owned.
 */
export interface AutonomousClassificationCandidate {
  ambiguity_indicators?: AmbiguityIndicators
  confidence: Confidence
  content_form: ContentForm
  core_new_fact?: CoreNewFact
  direct_relevance: DirectRelevance
  engineering_objects?: EngineeringObjects
  equipment_domains?: EquipmentDomains
  evidence_locators?: EvidenceLocators
  primary_type?: PrimaryIntelligenceType | null
  security_signals?: SecuritySignals
  specialty_facets?: SpecialtyFacets
}
