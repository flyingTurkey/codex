export type HasMore = boolean
export type Items = {
  [k: string]: string | number | boolean | null
}[]
export type NextCursor = string | null

export interface CursorPageDictStrUnionStrIntBoolNoneType {
  has_more: HasMore
  items: Items
  next_cursor?: NextCursor
}
