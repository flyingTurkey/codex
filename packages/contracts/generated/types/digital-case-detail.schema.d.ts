export type AiShortComment = null
export type Applicability = string[]
/**
 * @maxItems 30
 */
export type ApplicationScenarios = string[]
export type Attribution = string
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
export type Id = string
export type IndependentEvidenceIds = string[]
export type MetricName = string | null
export type NumericValue = string | null
export type Statement = string
export type Unit = string | null
export type OutcomeVerification = 'CLAIMED' | 'VERIFIED'
export type ClaimedOutcomes = DigitalCaseOutcome[]
export type DeploymentScale = string | null
/**
 * @maxItems 20
 */
export type EngineeringDomains = string[]
export type ClaimId = string
export type DigitalCaseEntityType = 'ORGANIZATION' | 'TECHNOLOGY' | 'PROJECT'
export type Id1 = string
export type Name = string
export type RelationType = string
export type Entities = DigitalCaseEntity[]
/**
 * @maxItems 20
 */
export type LifecycleStages = string[]
export type Limitations = string[]
export type MaturityLevel =
  | 'CONCEPT'
  | 'LAB_PROTOTYPE'
  | 'ENGINEERING_PROTOTYPE'
  | 'PILOT'
  | 'SINGLE_PROJECT_PRODUCTION'
  | 'MULTI_PROJECT_REPLICATION'
  | 'ENTERPRISE_SCALE'
  | 'UNKNOWN'
export type RecommendedAction = 'READ_ORIGINAL' | 'SAVE' | 'FOLLOW' | 'TECHNICAL_RESEARCH'
export type RecommendedActions = RecommendedAction[]
export type ReplicationConditions = string[]
export type Risks = string[]
/**
 * @maxItems 50
 */
export type TechnologyTags = string[]
export type VerifiedOutcomes = DigitalCaseOutcome[]

export interface DigitalCaseDetail {
  ai_short_comment?: AiShortComment
  applicability: Applicability
  application_scenarios: ApplicationScenarios
  claimed_outcomes: ClaimedOutcomes
  deployment_scale?: DeploymentScale
  engineering_domains: EngineeringDomains
  entities: Entities
  lifecycle_stages: LifecycleStages
  limitations: Limitations
  maturity_level: MaturityLevel
  recommended_actions: RecommendedActions
  replication_conditions: ReplicationConditions
  risks: Risks
  technology_tags: TechnologyTags
  verified_outcomes: VerifiedOutcomes
}
export interface DigitalCaseOutcome {
  attribution: Attribution
  evidence_ids: EvidenceIds
  id: Id
  independent_evidence_ids?: IndependentEvidenceIds
  metric_name?: MetricName
  numeric_value?: NumericValue
  statement: Statement
  unit?: Unit
  verification: OutcomeVerification
}
export interface DigitalCaseEntity {
  claim_id: ClaimId
  entity_type: DigitalCaseEntityType
  id: Id1
  name: Name
  relation_type: RelationType
}
