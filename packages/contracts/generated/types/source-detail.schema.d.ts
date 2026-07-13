export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2'
export type BaseUrl = string
export type SourceChannel = 'DIGITAL' | 'SAFETY' | 'BOTH'
export type CollectionMethod = string
export type CreatedAt = string
export type EffectiveActive = boolean
export type EffectiveActive1 = boolean
export type FixtureCount = number
export type FixtureSetSha256 = string | null
export type MissingReasons = string[]
export type OnboardingPolicyMatches = boolean
export type OnboardingValid = boolean
export type PolicyValid = boolean
export type RequiredChecksComplete = boolean
export type RequiredFixtureCount = number
export type Enabled = boolean
export type FixtureCount1 = number
export type Id = string
export type Name = string
export type Owner = string
export type PollIntervalMinutes = number
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

export interface SourceDetail {
  authority_level: AuthorityLevel
  base_url: BaseUrl
  channel: SourceChannel
  collection_method: CollectionMethod
  created_at: CreatedAt
  effective_active: EffectiveActive
  eligibility: SourceEligibility
  enabled: Enabled
  fixture_count: FixtureCount1
  id: Id
  name: Name
  owner: Owner
  poll_interval_minutes: PollIntervalMinutes
  priority: Priority
  registry_code: RegistryCode
  source_type: SourceType
  state: SourceState
}
export interface SourceEligibility {
  effective_active: EffectiveActive1
  fixture_count: FixtureCount
  fixture_set_sha256?: FixtureSetSha256
  missing_reasons: MissingReasons
  onboarding_policy_matches: OnboardingPolicyMatches
  onboarding_valid: OnboardingValid
  policy_valid: PolicyValid
  required_checks_complete: RequiredChecksComplete
  required_fixture_count?: RequiredFixtureCount
}
