export type FeedSuppressionAction = 'ACTIVATE' | 'REVOKE'
export type CreatedAt = string
export type EffectiveAt = string
export type FeedSuppressionFeedbackReason = 'OWNER_PREFERENCE' | 'CLASSIFICATION_ERROR' | 'SAFETY_DENIAL'
export type Id = string
export type FeedSuppressionScope =
  'EVENT' | 'PRIMARY_TYPE' | 'ENGINEERING_OBJECT' | 'SPECIALTY_FACET' | 'EQUIPMENT_DOMAIN' | 'SOURCE' | 'CUSTOM_TOPIC'
export type SupersedesRuleId = string | null
export type TargetKey = string

export interface FeedSuppressionRuleView {
  action: FeedSuppressionAction
  created_at: CreatedAt
  effective_at: EffectiveAt
  feedback_reason: FeedSuppressionFeedbackReason
  id: Id
  scope: FeedSuppressionScope
  supersedes_rule_id?: SupersedesRuleId
  target_key: TargetKey
}
