export type ConnectorType = 'RSS_ATOM' | 'JSON_API' | 'SITEMAP' | 'LIST_DETAIL' | 'DIRECT_PDF' | 'MANUAL_IMPORT'
export type DefinitionVersion = string
export type Reason = string

export interface ConnectorConfigRequest {
  config: Config
  connector_type: ConnectorType
  definition_version: DefinitionVersion
  reason: Reason
}
export interface Config {
  [k: string]: any
}
