export type ConnectorStabilityScore = number
export type ContentValidityScore = number
export type Eligible = boolean
export type EvaluatedAt = string
/**
 * @maxItems 100
 */
export type EvidenceRefs = string[]
export type ProfileEvidenceScore = number
/**
 * @maxItems 30
 */
export type ReasonCodes = string[]
export type RuleVersion = string
export type SampleCompletenessScore = number
export type SnapshotId = string
export type SourceId = string
export type TopicRelevanceScore = number
export type TotalScore = number

export interface SourceAutoScoreDetailView {
  component_explanations: ComponentExplanations
  connector_stability_score: ConnectorStabilityScore
  content_validity_score: ContentValidityScore
  eligible: Eligible
  evaluated_at: EvaluatedAt
  evidence_refs: EvidenceRefs
  hard_gate_results: HardGateResults
  profile_evidence_score: ProfileEvidenceScore
  reason_codes: ReasonCodes
  rule_version: RuleVersion
  sample_completeness_score: SampleCompletenessScore
  snapshot_id: SnapshotId
  source_id: SourceId
  topic_relevance_score: TopicRelevanceScore
  total_score: TotalScore
}
export interface ComponentExplanations {
  [k: string]: string
}
export interface HardGateResults {
  [k: string]: boolean
}
