export type AttemptCount = number
export type DecisionId = string | null
export type DocumentVersionId = string | null
export type Id = string
export type ExceptionKind = 'TECHNICAL' | 'SAFETY'
export type OpenedAt = string
export type SafetyOverrideability = 'OWNER_DECIDABLE' | 'HARD_BLOCK'
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
export type ResolvedAt = string | null
export type SourceId = string | null
export type SourceStreamId = string | null
export type OwnerExceptionStatus = 'OPEN' | 'RESOLVED'
export type UpdatedAt = string
export type Version = number

export interface OwnerExceptionView {
  attempt_count: AttemptCount
  decision_id?: DecisionId
  document_version_id?: DocumentVersionId
  id: Id
  kind: ExceptionKind
  opened_at: OpenedAt
  overrideability?: SafetyOverrideability | null
  reason_codes: ReasonCodes
  resolved_at?: ResolvedAt
  source_id?: SourceId
  source_stream_id?: SourceStreamId
  status: OwnerExceptionStatus
  updated_at: UpdatedAt
  version: Version
}
