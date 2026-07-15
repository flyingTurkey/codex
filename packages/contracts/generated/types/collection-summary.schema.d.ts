export type Archived = boolean
export type CreatedAt = string
export type Id = string
export type ItemCount = number
export type Name = string
export type UpdatedAt = string
export type Version = number

export interface CollectionSummary {
  archived: Archived
  created_at: CreatedAt
  id: Id
  item_count: ItemCount
  name: Name
  updated_at: UpdatedAt
  version: Version
}
