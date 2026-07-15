export type ItemId = string
export type Value = 'USEFUL' | 'NOT_USEFUL'

export interface FeedbackRequest {
  item_id: ItemId
  value: Value
}
