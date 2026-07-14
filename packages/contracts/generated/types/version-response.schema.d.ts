export type ApiVersion = 'v1'
export type ContentSchemaVersion = '1.1.0'

export interface VersionResponse {
  api_version?: ApiVersion
  content_schema_version?: ContentSchemaVersion
}
