export type BundleSha256 = string
export type CandidateId = string
export type Code = string
/**
 * @maxItems 50
 */
export type EvidenceRefs = string[]
export type QualificationCheckLevel = 'PASS' | 'WARN' | 'BLOCK'
export type Message = string
export type ObservedAt = string
/**
 * @maxItems 100
 */
export type Checks = QualificationCheckView[]
export type CreatedAt = string
/**
 * How qualification evidence may be captured, independent of display policy.
 */
export type EvidenceCapturePolicy = 'PRIVATE_RAW_ALLOWED' | 'TRANSIENT_METADATA_ONLY'
export type ExpiresAt = string
export type Id = string
export type MaterialFingerprint = string
/**
 * @maxItems 100
 */
export type ReasonCodes = string[]
export type RelevantItemCount = number
export type RuleVersion = string
export type RunId = string
export type SampledItemCount = number
export type StoragePolicy = 'RAW_EVIDENCE_ALLOWED' | 'METADATA_ONLY' | 'LINK_ONLY'
export type QualificationVerdict = 'QUALIFIED' | 'WARN_WAIVABLE' | 'BLOCKED'
export type CandidateId1 = string
export type CompletedAt = string | null
export type CreatedAt1 = string
export type FailureCode = string | null
export type Id1 = string
export type RequestedBy = string
export type RuleVersion1 = string
export type StartedAt = string | null
export type QualificationRunStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'

export interface QualificationRunView {
  bundle?: QualificationBundleView | null
  candidate_id: CandidateId1
  completed_at?: CompletedAt
  created_at: CreatedAt1
  failure_code?: FailureCode
  id: Id1
  requested_by: RequestedBy
  rule_version: RuleVersion1
  started_at?: StartedAt
  status: QualificationRunStatus
}
export interface QualificationBundleView {
  bundle_sha256: BundleSha256
  candidate_id: CandidateId
  checks?: Checks
  created_at: CreatedAt
  evidence_capture_policy?: EvidenceCapturePolicy
  expires_at: ExpiresAt
  id: Id
  material_fingerprint: MaterialFingerprint
  reason_codes?: ReasonCodes
  relevant_item_count: RelevantItemCount
  rule_version: RuleVersion
  run_id: RunId
  sampled_item_count: SampledItemCount
  storage_policy: StoragePolicy
  verdict: QualificationVerdict
}
export interface QualificationCheckView {
  code: Code
  evidence_refs?: EvidenceRefs
  level: QualificationCheckLevel
  message: Message
  observed_at: ObservedAt
}
