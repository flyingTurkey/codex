export type Archived = boolean | null
export type Name = string | null

export interface CollectionPatchRequest {
  archived?: Archived
  name?: Name
}
