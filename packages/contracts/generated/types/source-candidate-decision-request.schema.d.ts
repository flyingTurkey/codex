export type SourceCandidateDecision = 'ENABLE' | 'DISMISS'
export type ExpectedBundleSha256 = string | null
export type Reason = string
export type WaiverReason = string | null

export interface SourceCandidateDecisionRequest {
  decision: SourceCandidateDecision
  expected_bundle_sha256?: ExpectedBundleSha256
  reason: Reason
  waiver_reason?: WaiverReason
}
