export type AggregateEffectiveActions = number
export type DistinctFeedbackUsers = number
export type EndedAt = string
export type IdentityMetricsAvailable = false
export type StartedAt = string
export type SufficientWindow = boolean
export type TotalVotes = number
export type UsefulVotes = number

export interface PilotMetrics {
  aggregate_effective_actions: AggregateEffectiveActions
  distinct_feedback_users: DistinctFeedbackUsers
  ended_at: EndedAt
  identity_metrics_available?: IdentityMetricsAvailable
  started_at: StartedAt
  sufficient_window: SufficientWindow
  total_votes: TotalVotes
  useful_votes: UsefulVotes
}
