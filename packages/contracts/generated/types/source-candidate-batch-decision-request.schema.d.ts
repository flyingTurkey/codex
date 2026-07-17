export type ExpectedRuleVersion = string
export type Reason = string
export type CandidateId = string
export type ExpectedBundleSha256 = string
/**
 * @minItems 1
 * @maxItems 10
 */
export type Targets = SourceCandidateBatchTarget[]

export interface SourceCandidateBatchDecisionRequest {
  expected_rule_version: ExpectedRuleVersion
  reason: Reason
  targets: Targets
}
export interface SourceCandidateBatchTarget {
  candidate_id: CandidateId
  expected_bundle_sha256: ExpectedBundleSha256
}
