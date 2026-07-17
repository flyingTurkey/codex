export type Eligible = boolean
export type EvaluatedAt = string
/**
 * @maxItems 30
 */
export type ReasonCodes = string[]
export type RuleVersion = string
export type SnapshotId = string
export type TotalScore = number

export interface SourceAutoScoreSummaryView {
  eligible: Eligible
  evaluated_at: EvaluatedAt
  reason_codes: ReasonCodes
  rule_version: RuleVersion
  snapshot_id: SnapshotId
  total_score: TotalScore
}
