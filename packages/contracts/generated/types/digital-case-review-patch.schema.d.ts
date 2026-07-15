/**
 * @maxItems 30
 */
export type ApplicationScenarios = string[]
/**
 * @maxItems 20
 */
export type EngineeringDomains = string[]
/**
 * @maxItems 20
 */
export type LifecycleStages = string[]
export type MaturityEvidenceIds = string[]
export type MaturityLevel =
  | 'CONCEPT'
  | 'LAB_PROTOTYPE'
  | 'ENGINEERING_PROTOTYPE'
  | 'PILOT'
  | 'SINGLE_PROJECT_PRODUCTION'
  | 'MULTI_PROJECT_REPLICATION'
  | 'ENTERPRISE_SCALE'
  | 'UNKNOWN'
export type AttributionEntityId = string
export type IndependentEvidenceIds = string[]
export type OutcomeId = string
export type OutcomeVerification = 'CLAIMED' | 'VERIFIED'
export type OutcomeAttributions = DigitalOutcomeAttributionPatch[]
/**
 * @maxItems 50
 */
export type TechnologyTags = string[]

export interface DigitalCaseReviewPatch {
  application_scenarios: ApplicationScenarios
  engineering_domains: EngineeringDomains
  lifecycle_stages: LifecycleStages
  maturity_evidence_ids: MaturityEvidenceIds
  maturity_level: MaturityLevel
  outcome_attributions: OutcomeAttributions
  technology_tags: TechnologyTags
}
export interface DigitalOutcomeAttributionPatch {
  attribution_entity_id: AttributionEntityId
  independent_evidence_ids?: IndependentEvidenceIds
  outcome_id: OutcomeId
  verification: OutcomeVerification
}
