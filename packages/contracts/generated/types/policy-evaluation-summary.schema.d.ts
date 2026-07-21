export type AuthorizesProduction = false
export type AutoAcceptedCount = number
export type AutoFilteredCount = number
export type BenchmarkVersion = string
export type CorpusManifestSha256 = string
export type EvaluatedAt = string
export type GatePassed = boolean
export type Id = string
export type LockedNegativeLeaks = number
export type PolicyEvaluationMode = 'OFFLINE_REPLAY' | 'SHADOW'
export type NewOwnerSemanticTasks = 0
export type OwnerSuppressedCount = number
export type AiModel = string
export type AiProvider = string
export type BundleSha256 = string
export type CodeVersion = string
export type GlobalRuleVersion = string
export type PolicyVersion = string
export type PromptVersion = string
export type SchemaVersion = string
export type SourceStreamPolicyVersion = string
export type PrecisionBps = number
export type RecallBps = number
export type SafetyHoldCount = number
export type SchemaValidBps = number
export type TechnicalFailedCount = number
export type TechnicalRetryCount = number
export type TotalCases = number

export interface PolicyEvaluationSummary {
  authorizes_production: AuthorizesProduction
  auto_accepted_count: AutoAcceptedCount
  auto_filtered_count: AutoFilteredCount
  benchmark_version: BenchmarkVersion
  corpus_manifest_sha256: CorpusManifestSha256
  evaluated_at: EvaluatedAt
  gate_passed: GatePassed
  id: Id
  locked_negative_leaks: LockedNegativeLeaks
  mode: PolicyEvaluationMode
  new_owner_semantic_tasks: NewOwnerSemanticTasks
  owner_suppressed_count?: OwnerSuppressedCount
  policy: QualificationPolicyIdentity
  precision_bps: PrecisionBps
  recall_bps: RecallBps
  safety_hold_count?: SafetyHoldCount
  schema_valid_bps: SchemaValidBps
  technical_failed_count?: TechnicalFailedCount
  technical_retry_count?: TechnicalRetryCount
  total_cases: TotalCases
}
export interface QualificationPolicyIdentity {
  ai_model: AiModel
  ai_provider: AiProvider
  bundle_sha256: BundleSha256
  code_version: CodeVersion
  global_rule_version: GlobalRuleVersion
  policy_version: PolicyVersion
  prompt_version: PromptVersion
  schema_version: SchemaVersion
  source_stream_policy_version: SourceStreamPolicyVersion
}
