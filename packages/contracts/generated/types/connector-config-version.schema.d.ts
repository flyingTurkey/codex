export type AllowedHosts = string[]
export type ConfigSha256 = string
export type ConnectorType = 'RSS_ATOM' | 'JSON_API' | 'SITEMAP' | 'LIST_DETAIL' | 'DIRECT_PDF' | 'MANUAL_IMPORT'
export type CreatedAt = string
export type CreatedBy = string
export type CredentialConfigured = boolean
export type DefinitionVersion = string
export type Id = string
export type PolicyVersionId = string
export type SourceId = string
export type ValidationStatus = 'VALID' | 'INVALID'
export type VersionNumber = number

export interface ConnectorConfigVersionView {
  allowed_hosts: AllowedHosts
  config: Config
  config_sha256: ConfigSha256
  connector_type: ConnectorType
  created_at: CreatedAt
  created_by: CreatedBy
  credential_configured: CredentialConfigured
  definition_version: DefinitionVersion
  id: Id
  policy_version_id: PolicyVersionId
  source_id: SourceId
  validation_status: ValidationStatus
  version_number: VersionNumber
}
export interface Config {
  [k: string]: any
}
