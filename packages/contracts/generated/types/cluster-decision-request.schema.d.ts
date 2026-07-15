export type Action = 'MERGE' | 'SPLIT' | 'KEEP_DISTINCT' | 'LINK_RELATION'
/**
 * @minItems 2
 * @maxItems 1000
 */
export type MemberIds = string[]
export type Reason = string
export type RelationType = string | null

export interface ClusterDecisionRequest {
  action: Action
  member_ids: MemberIds
  reason: Reason
  relation_type?: RelationType
}
