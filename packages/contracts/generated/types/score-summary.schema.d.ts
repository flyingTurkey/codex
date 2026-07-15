export type CalculatedAt = string
export type ScoreDimension =
  'RELEVANCE' | 'AUTHORITY' | 'IMPACT' | 'NOVELTY' | 'TIMELINESS' | 'EVIDENCE' | 'CONFIDENCE' | 'HEAT'
export type Code = string
export type Explanation = string
export type Label = string
export type Points = number
/**
 * @maxItems 20
 */
export type Features = ScoreFeature[]
export type Overridden = boolean
export type OverrideReason = string | null
export type RawScore = number
export type RuleVersion = 'scoring-v1.0.0'
export type Score = number

export interface ScoreSummary {
  authority?: ScoreDimensionSummary | null
  confidence?: ScoreDimensionSummary | null
  evidence?: ScoreDimensionSummary | null
  heat?: ScoreDimensionSummary | null
  impact?: ScoreDimensionSummary | null
  novelty?: ScoreDimensionSummary | null
  relevance?: ScoreDimensionSummary | null
  timeliness?: ScoreDimensionSummary | null
}
export interface ScoreDimensionSummary {
  calculated_at: CalculatedAt
  dimension: ScoreDimension
  features: Features
  overridden?: Overridden
  override_reason?: OverrideReason
  raw_score: RawScore
  rule_version: RuleVersion
  score: Score
}
export interface ScoreFeature {
  code: Code
  explanation: Explanation
  label: Label
  points: Points
}
