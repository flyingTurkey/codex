export type AutoMergeEnabled = false
export type EvaluationTier = 'INTERNAL_TEST_FIXTURE' | 'HUMAN_GOLD'
export type GeneratedAt = string
export type Channel = 'DIGITAL' | 'SAFETY' | 'INDUSTRY'
export type EventCount = number
export type HeatScore = number
export type Id = string
export type IndependentSourceCount = number
export type LatestActivityAt = string
export type RuleVersion = 'scoring-v1.0.0'
export type Title = string
export type Items = HotTopicSummary[]
export type NextCursor = string | null

export interface HotTopicPage {
  auto_merge_enabled?: AutoMergeEnabled
  evaluation_tier: EvaluationTier
  generated_at: GeneratedAt
  items: Items
  next_cursor?: NextCursor
}
export interface HotTopicSummary {
  domain: Channel
  event_count: EventCount
  heat_score: HeatScore
  id: Id
  independent_source_count: IndependentSourceCount
  latest_activity_at: LatestActivityAt
  rule_version: RuleVersion
  title: Title
}
