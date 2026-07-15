export type ApiVersion = 'v1'
export type ContentSchemaVersion = '1.1.0'
export type SearchSchemaVersion = '1.0.0'
export type SemanticSearchEnabled = boolean

export interface VersionResponse {
  api_version?: ApiVersion
  content_schema_version?: ContentSchemaVersion
  search_schema_version?: SearchSchemaVersion
  semantic_search_enabled?: SemanticSearchEnabled
}
