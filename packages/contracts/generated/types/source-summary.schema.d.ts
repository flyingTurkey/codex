export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2'
export type BaseUrl = string
export type SourceChannel = 'DIGITAL' | 'SAFETY' | 'BOTH'
export type CreatedAt = string
export type EffectiveActive = boolean
export type Enabled = boolean
export type FixtureCount = number
export type Id = string
export type Name = string
export type Priority = string
export type RegistryCode = string | null
export type SourceType =
  | 'government'
  | 'standards'
  | 'journal'
  | 'research_institute'
  | 'association'
  | 'enterprise'
  | 'media'
  | 'academic_api'
  | 'academic_database'
export type SourceState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'FIXTURE_TEST' | 'APPROVED' | 'ACTIVE'

export interface SourceSummary {
  authority_level: AuthorityLevel
  base_url: BaseUrl
  channel: SourceChannel
  created_at: CreatedAt
  effective_active: EffectiveActive
  enabled: Enabled
  fixture_count: FixtureCount
  id: Id
  name: Name
  priority: Priority
  registry_code: RegistryCode
  source_type: SourceType
  state: SourceState
}
