export type AssessedAt = string
/**
 * @maxItems 50
 */
export type EvidenceRefs = string[]
export type AuthorityLevel = 'A0' | 'A1' | 'B1' | 'B2' | 'C1' | 'C2' | 'UNKNOWN'
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type RuleVersion = string
export type AssessedAt1 = string
/**
 * @maxItems 50
 */
export type EvidenceRefs1 = string[]
export type SourceIndependenceLevel =
  'EDITORIALLY_INDEPENDENT' | 'PARTIALLY_INDEPENDENT' | 'NOT_INDEPENDENT' | 'UNKNOWN'
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes1 = string[]
export type RuleVersion1 = string
export type Reason = string

/**
 * Append-only explainable authority and independence assessments.
 */
export interface SourceAssessmentSubmission {
  authority: SourceAuthorityAssessment
  independence: SourceIndependenceAssessment
  reason: Reason
}
export interface SourceAuthorityAssessment {
  assessed_at: AssessedAt
  evidence_refs?: EvidenceRefs
  level: AuthorityLevel
  reason_codes: ReasonCodes
  rule_version: RuleVersion
}
export interface SourceIndependenceAssessment {
  assessed_at: AssessedAt1
  evidence_refs?: EvidenceRefs1
  level: SourceIndependenceLevel
  reason_codes: ReasonCodes1
  rule_version: RuleVersion1
}
