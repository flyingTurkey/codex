export type ConnectorType = 'RSS_ATOM' | 'JSON_API' | 'SITEMAP' | 'LIST_DETAIL' | 'DIRECT_PDF' | 'MANUAL_IMPORT'
export type DefinitionVersion = string
export type NetworkIoPerformed = false
export type SchemaSha256 = string
export type SchemaVersion = string

export interface ConnectorConfigPreview {
  config: Config
  connector_type: ConnectorType
  definition_version: DefinitionVersion
  network_io_performed: NetworkIoPerformed
  schema_sha256: SchemaSha256
  schema_version: SchemaVersion
}
export interface Config {
  [k: string]: any
}
