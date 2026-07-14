export type EventId = string
export type FromItemId = string
export type Id = string
export type EventRelation = 'FOLLOW_UP' | 'INVESTIGATES' | 'PENALIZES' | 'RECTIFIES' | 'CORRECTS'
export type ReviewedAt = string
export type ReviewedBy = string
export type ToItemId = string

export interface EventRelationView {
  event_id: EventId
  from_item_id: FromItemId
  id: Id
  relation_type: EventRelation
  reviewed_at: ReviewedAt
  reviewed_by: ReviewedBy
  to_item_id: ToItemId
}
