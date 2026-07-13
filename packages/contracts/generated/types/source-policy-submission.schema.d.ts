/**
 * @minItems 1
 */
export type AllowedDomains = [string, ...string[]]
export type RateLimitPerMinute = number
export type RequiresAuth = boolean
export type UserAgent = string
export type AttributionTemplate = string
export type DisplayPolicy = 'METADATA_EXCERPT_LINK' | 'OFFICIAL_READER_LINK' | 'LINK_ONLY'
export type ExcerptMaxChars = number
export type FulltextAllowed = boolean
export type ImageAllowed = boolean
export type StoragePolicy = 'RAW_EVIDENCE_ALLOWED' | 'METADATA_ONLY' | 'LINK_ONLY'
export type PolicyVersion = string
export type ApprovalId = string
export type ValidUntil = string
export type CheckedAt = string
export type EvidenceSha256 = string | null
export type EvidenceUrl = string
export type ReviewEvidenceResult = 'ALLOWED' | 'RESTRICTED' | 'NOT_PRESENT' | 'BLOCKED'
export type SourcePolicyStatus = 'DRAFT' | 'VALID' | 'EXPIRED' | 'REVOKED'

export interface SourcePolicySubmission {
  access: SourceAccessPolicy
  copyright: CopyrightPolicy
  policy_version: PolicyVersion
  review: SourcePolicyReviewSubmission
  robots_review: ReviewEvidence
  status: SourcePolicyStatus
  terms_review: ReviewEvidence
}
export interface SourceAccessPolicy {
  allowed_domains: AllowedDomains
  rate_limit_per_minute: RateLimitPerMinute
  requires_auth: RequiresAuth
  user_agent: UserAgent
}
export interface CopyrightPolicy {
  attribution_template: AttributionTemplate
  display_policy: DisplayPolicy
  excerpt_max_chars: ExcerptMaxChars
  fulltext_allowed: FulltextAllowed
  image_allowed: ImageAllowed
  storage_policy: StoragePolicy
}
export interface SourcePolicyReviewSubmission {
  approval_id: ApprovalId
  valid_until: ValidUntil
}
export interface ReviewEvidence {
  checked_at: CheckedAt
  evidence_sha256?: EvidenceSha256
  evidence_url: EvidenceUrl
  result: ReviewEvidenceResult
}
