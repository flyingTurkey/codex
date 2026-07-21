export type FeedSuppressionAction = 'ACTIVATE' | 'REVOKE'
export type FeedSuppressionFeedbackReason = 'OWNER_PREFERENCE' | 'CLASSIFICATION_ERROR' | 'SAFETY_DENIAL'
export type FeedSuppressionScope =
  'EVENT' | 'PRIMARY_TYPE' | 'ENGINEERING_OBJECT' | 'SPECIALTY_FACET' | 'EQUIPMENT_DOMAIN' | 'SOURCE' | 'CUSTOM_TOPIC'
export type SupersedesRuleId = string | null
export type TargetKey = string

export interface FeedSuppressionCommand {
  action: FeedSuppressionAction
  feedback_reason: FeedSuppressionFeedbackReason
  scope: FeedSuppressionScope
  supersedes_rule_id?: SupersedesRuleId
  target_key: TargetKey
}
