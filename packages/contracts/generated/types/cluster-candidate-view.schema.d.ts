export type CreatedAt = string
/**
 * @maxItems 30
 */
export type FeatureExplanations = string[]
/**
 * @maxItems 10
 */
export type HardConflicts = string[]
export type Id = string
export type Kind = 'DUPLICATE' | 'EVENT' | 'TOPIC' | 'RELATION'
/**
 * @minItems 2
 * @maxItems 1000
 */
export type MemberIds = string[]
export type RelationType = string | null
export type ScoreBps = number | null
export type Status = 'PENDING_REVIEW' | 'ACCEPTED' | 'REJECTED'

export interface ClusterCandidateView {
  created_at: CreatedAt
  feature_explanations: FeatureExplanations
  hard_conflicts: HardConflicts
  id: Id
  kind: Kind
  member_ids: MemberIds
  relation_type?: RelationType
  score_bps?: ScoreBps
  status: Status
}
