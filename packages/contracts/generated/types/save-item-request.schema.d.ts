export type CollectionId = string | null
export type ItemId = string

export interface SaveItemRequest {
  collection_id?: CollectionId
  item_id: ItemId
}
