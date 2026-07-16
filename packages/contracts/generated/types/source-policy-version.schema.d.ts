export type CreatedAt = string
export type DecidedBy = string | null
export type DocumentSha256 = string
export type Id = string
export type PolicyVersion = string
export type SchemaVersion = string
export type SourceId = string
export type Status = string
export type SubmittedBy = string
export type ValidFrom = string
export type ValidUntil = string

export interface SourcePolicyVersionView {
  created_at: CreatedAt
  decided_by?: DecidedBy
  document: Document
  document_sha256: DocumentSha256
  id: Id
  policy_version: PolicyVersion
  schema_version: SchemaVersion
  source_id: SourceId
  status: Status
  submitted_by: SubmittedBy
  valid_from: ValidFrom
  valid_until: ValidUntil
}
export interface Document {
  [k: string]: any
}
