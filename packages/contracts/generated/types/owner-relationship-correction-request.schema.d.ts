export type Action = 'WITHDRAW_RELATION' | 'SPLIT_EVENT' | 'KEEP_INDEPENDENT' | 'CORRECT_MODEL_RELATION'
export type ChildEventId = string
export type ItemId = string
/**
 * @maxItems 1000
 */
export type Allocations = EventSplitAllocation[]
export type CommandId = string
export type CorrectedKind = ('MODEL_ALIAS' | 'VERSION_SUCCESSOR') | null
export type CorrectedSourceItemId = string | null
export type CorrectedTargetItemId = string | null
export type DecisionId = string | null
/**
 * @maxItems 1000
 */
export type MemberItemIds = string[]
export type Reason = string

export interface OwnerRelationshipCorrectionRequest {
  action: Action
  allocations?: Allocations
  command_id: CommandId
  corrected_kind?: CorrectedKind
  corrected_source_item_id?: CorrectedSourceItemId
  corrected_target_item_id?: CorrectedTargetItemId
  decision_id?: DecisionId
  member_item_ids?: MemberItemIds
  reason: Reason
}
export interface EventSplitAllocation {
  child_event_id: ChildEventId
  item_id: ItemId
}
