export type AffectsProduction = false
export type DecidedAt = string
export type AutomatedDisposition =
  'AUTO_ACCEPTED' | 'AUTO_FILTERED' | 'TECHNICAL_RETRY' | 'TECHNICAL_FAILED' | 'SAFETY_HOLD' | 'OWNER_SUPPRESSED'
export type DocumentVersionId = string
export type EvaluationId = string
export type Id = string
export type AutomatedDecisionReason =
  | 'POLICY_ACCEPTED'
  | 'RULE_LOCKED_NEGATIVE'
  | 'RULE_NO_ENGINEERING_COOCCURRENCE'
  | 'RULE_PRIMARY_TYPE_UNSUPPORTED'
  | 'RULE_AXIS_INVARIANT_FAILED'
  | 'RULE_PROMPT_INJECTION'
  | 'AI_SCHEMA_INVALID'
  | 'AI_RULE_CONFLICT'
  | 'AI_AMBIGUITY_UNRESOLVED'
  | 'EVIDENCE_MISSING'
  | 'EVIDENCE_LOCATOR_INVALID'
  | 'DOCUMENT_VERSION_STALE'
  | 'SAFETY_SIGNAL'
  | 'TECHNICAL_RETRYABLE'
  | 'TECHNICAL_EXHAUSTED'
  | 'OWNER_PREFERENCE'
  | 'OWNER_CLASSIFICATION_ERROR'
  | 'POLICY_GATE_FAILED'
/**
 * @minItems 1
 * @maxItems 20
 */
export type ReasonCodes = AutomatedDecisionReason[]

export interface ShadowDecisionView {
  affects_production: AffectsProduction
  decided_at: DecidedAt
  disposition: AutomatedDisposition
  document_version_id: DocumentVersionId
  evaluation_id: EvaluationId
  id: Id
  reason_codes: ReasonCodes
}
