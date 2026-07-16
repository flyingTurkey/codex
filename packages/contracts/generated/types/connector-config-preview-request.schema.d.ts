export type ConnectorType = 'RSS_ATOM' | 'JSON_API' | 'SITEMAP' | 'LIST_DETAIL' | 'DIRECT_PDF' | 'MANUAL_IMPORT'
export type DefinitionVersion = string

export interface ConnectorConfigPreviewRequest {
  config: Config
  connector_type: ConnectorType
  definition_version: DefinitionVersion
}
export interface Config {
  [k: string]: any
}
