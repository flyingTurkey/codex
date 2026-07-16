export type Capabilities = string[]
export type ConnectorType = 'RSS_ATOM' | 'JSON_API' | 'SITEMAP' | 'LIST_DETAIL' | 'DIRECT_PDF' | 'MANUAL_IMPORT'
export type DefinitionVersion = string
export type ExecutorKey = string
export type Id = string
export type SchemaSha256 = string
export type SchemaVersion = string

export interface ConnectorDefinitionView {
  capabilities: Capabilities
  connector_type: ConnectorType
  definition_version: DefinitionVersion
  executor_key: ExecutorKey
  id: Id
  schema_document: SchemaDocument
  schema_sha256: SchemaSha256
  schema_version: SchemaVersion
}
export interface SchemaDocument {
  [k: string]: any
}
