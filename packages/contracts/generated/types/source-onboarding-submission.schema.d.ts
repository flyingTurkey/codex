export type Code = string
export type EvidenceRef = string
export type EvidenceSha256 = string | null
/**
 * @minItems 11
 */
export type Checks = OnboardingCheckEvidence[]
export type ValidUntil = string

export interface SourceOnboardingSubmission {
  checks: Checks
  valid_until: ValidUntil
}
export interface OnboardingCheckEvidence {
  code: Code
  evidence_ref: EvidenceRef
  evidence_sha256?: EvidenceSha256
}
