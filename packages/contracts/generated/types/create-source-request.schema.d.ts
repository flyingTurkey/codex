export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2'
export type BaseUrl = string
export type SourceChannel = 'DIGITAL' | 'SAFETY' | 'BOTH'
export type CollectionMethod = string
export type Name = string
export type Owner = string
export type PollIntervalMinutes = number
export type Priority = 'P0' | 'P1' | 'P2'
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

export interface CreateSourceRequest {
  authority_level: AuthorityLevel
  base_url: BaseUrl
  channel: SourceChannel
  collection_method: CollectionMethod
  name: Name
  owner: Owner
  poll_interval_minutes: PollIntervalMinutes
  priority: Priority
  source_type: SourceType
}
