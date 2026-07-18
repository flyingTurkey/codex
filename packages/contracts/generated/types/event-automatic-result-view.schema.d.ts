/**
 * @maxItems 20
 */
export type FailureReasonCodes = string[]
/**
 * @maxItems 10
 */
export type CurrentLimitations = string[]
/**
 * @maxItems 10
 */
export type PotentialEngineeringScenarios = string[]
/**
 * @maxItems 10
 */
export type PotentialIndustryImpacts = string[]
/**
 * @maxItems 10
 */
export type QuestionsToVerify = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type UsedClaimIds = string[]
export type WhyWorthAttention = string
export type OriginalUrl = string
export type ResultType = 'EVIDENCE_FACT' | 'AI_JUDGMENT' | 'UNVERIFIED_AI' | 'AI_PROCESSING_FAILED'
export type SignalId = string
export type Title = string

export interface EventAutomaticResultView {
  failure_reason_codes?: FailureReasonCodes
  judgment?: AiJudgmentSignal | null
  original_url: OriginalUrl
  result_type: ResultType
  signal_id: SignalId
  title: Title
}
export interface AiJudgmentSignal {
  current_limitations?: CurrentLimitations
  potential_engineering_scenarios?: PotentialEngineeringScenarios
  potential_industry_impacts?: PotentialIndustryImpacts
  questions_to_verify?: QuestionsToVerify
  used_claim_ids: UsedClaimIds
  why_worth_attention: WhyWorthAttention
}
