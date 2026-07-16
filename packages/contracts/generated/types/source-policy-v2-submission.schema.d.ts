export type AutomaticPublicationPolicy = 'DISABLED' | 'PUBLICATION_GATE_ELIGIBLE'
export type CheckedAt = string
export type EvidenceSha256 = string | null
export type EvidenceUrl = string
export type ReviewEvidenceResult = 'ALLOWED' | 'RESTRICTED' | 'NOT_PRESENT' | 'BLOCKED'
export type DisplayPolicy = 'METADATA_EXCERPT_LINK' | 'OFFICIAL_READER_LINK' | 'LINK_ONLY'
export type DownloadPolicy = 'DISABLED' | 'ORIGINAL_LINK_ONLY' | 'SIGNED_INTERNAL_COPY'
/**
 * @minItems 1
 * @maxItems 100
 */
export type AllowedDomains = string[]
export type MinimumIntervalSeconds = number
export type RateLimitPerMinute = number
export type UserAgent = string
export type LegalHoldPolicy = 'SUPPORTED' | 'NOT_APPLICABLE'
export type PolicyVersion = string
export type Reason = string
export type DeleteAfterRetention = boolean
export type RetentionDays = number
export type SchemaVersion = '2.0.0'
export type SloApplicability = 'APPLICABLE' | 'NOT_APPLICABLE'
export type AuthorizationConfirmed = boolean
export type Reason1 = string | null
export type TargetMinutes = number | null
export type TechnicalConditionsConfirmed = boolean
export type StoragePolicy = 'RAW_EVIDENCE_ALLOWED' | 'METADATA_ONLY' | 'LINK_ONLY'
export type ValidFrom = string
export type ValidUntil = string

/**
 * Declarative policy input; status and approval are server-owned facts.
 */
export interface SourcePolicyV2Submission {
  automatic_publication: AutomaticPublicationPolicy
  copyright_review: ReviewEvidence
  display_policy: DisplayPolicy
  download_policy: DownloadPolicy
  fetch: SourceFetchPolicy
  legal_hold_policy: LegalHoldPolicy
  policy_version: PolicyVersion
  reason: Reason
  retention: SourceRetentionPolicy
  robots_review: ReviewEvidence
  schema_version: SchemaVersion
  slo: SourceSloPolicy
  storage_policy: StoragePolicy
  terms_review: ReviewEvidence
  valid_from: ValidFrom
  valid_until: ValidUntil
}
export interface ReviewEvidence {
  checked_at: CheckedAt
  evidence_sha256?: EvidenceSha256
  evidence_url: EvidenceUrl
  result: ReviewEvidenceResult
}
export interface SourceFetchPolicy {
  allowed_domains: AllowedDomains
  minimum_interval_seconds: MinimumIntervalSeconds
  rate_limit_per_minute: RateLimitPerMinute
  user_agent: UserAgent
}
export interface SourceRetentionPolicy {
  delete_after_retention: DeleteAfterRetention
  retention_days: RetentionDays
}
export interface SourceSloPolicy {
  applicability: SloApplicability
  authorization_confirmed: AuthorizationConfirmed
  reason?: Reason1
  target_minutes?: TargetMinutes
  technical_conditions_confirmed: TechnicalConditionsConfirmed
}
