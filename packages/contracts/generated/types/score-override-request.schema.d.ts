export type ScoreDimension =
  'RELEVANCE' | 'AUTHORITY' | 'IMPACT' | 'NOVELTY' | 'TIMELINESS' | 'EVIDENCE' | 'CONFIDENCE' | 'HEAT'
export type Reason = string
export type Score = number

export interface ScoreOverrideRequest {
  dimension: ScoreDimension
  reason: Reason
  score: Score
}
