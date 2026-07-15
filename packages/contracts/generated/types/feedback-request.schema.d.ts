export type EventId = string | null
export type ItemId = string | null
export type Value = 'USEFUL' | 'NOT_USEFUL'

export interface FeedbackRequest {
  event_id?: EventId
  item_id?: ItemId
  value: Value
}
