export type CaseId = string
export type Command =
  | 'ACCEPT_CLAIM'
  | 'REJECT_CLAIM'
  | 'REPLACE_CLAIM'
  | 'APPROVE_AI_SUMMARY'
  | 'REJECT_AI_SUMMARY'
  | 'REGENERATE_AI_SUMMARY'
export type CreatedAt = string
export type DecisionId = string
/**
 * @maxItems 500
 */
export type AiSummaryDecisions = ContentReviewDecisionV2[]
export type ClaimBasisV2 =
  | 'MANUFACTURER_CLAIM'
  | 'RESEARCH_CONCLUSION'
  | 'PROJECT_FIRST_PARTY_RECORD'
  | 'INDEPENDENT_VERIFICATION'
  | 'AUTHORITY_FINDING'
export type ClaimId = string
/**
 * @minItems 1
 * @maxItems 100
 */
export type EvidenceLocators = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type Claims = ContentPreparationClaimV2[]
/**
 * @maxItems 500
 */
export type FactDecisions = ContentReviewDecisionV2[]
export type InvalidationReason =
  ('DOCUMENT_VERSION_CHANGED' | 'ACCEPTED_CLAIMS_CHANGED' | 'SOURCE_WITHDRAWN' | 'SOURCE_CORRECTED') | null
/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type EvidenceLocators1 = string[]
export type Text = string
export type Status = 'CURRENT' | 'STALE'
/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds1 = string[]
export type JudgmentType = null
export type Kind = 'FACT'
export type Section = 'WHAT_HAPPENED'
export type Text1 = string
/**
 * @maxItems 0
 */
export type ClaimIds2 = string[]
export type JudgmentType1 = 'ENGINEERING_SIGNIFICANCE' | 'LIMITATION_AND_FOLLOW_UP'
export type Kind1 = 'JUDGMENT'
export type Section1 = 'ENGINEERING_IMPACT' | 'LIMITATIONS_AND_FOLLOW_UP'
export type Text2 = string
/**
 * @minItems 3
 * @maxItems 12
 */
export type Paragraphs = (ContentSummaryFactParagraphV2 | ContentSummaryJudgmentParagraphV2)[]
export type VisibleCharacterCount = number
export type CreatedAt1 = string
export type DocumentVersionId = string
export type EventId = string | null
export type ProcessingState = 'IDLE' | 'QUEUED' | 'PROCESSING' | 'FAILED'
export type Reason = string
export type RiskTier = 'R1' | 'R2' | 'R3' | 'R4'
export type State = 'OPEN' | 'RESOLVED' | 'QUARANTINED'
export type UpdatedAt = string
export type Version = number

export interface ReviewCaseV2 {
  case_id: CaseId
  content_preparation?: ContentPreparationReviewV2 | null
  created_at: CreatedAt1
  document_version_id: DocumentVersionId
  event_id?: EventId
  processing_state?: ProcessingState
  reason: Reason
  risk_tier: RiskTier
  safe_metadata: SafeMetadata
  state: State
  updated_at: UpdatedAt
  version: Version
}
export interface ContentPreparationReviewV2 {
  ai_summary_decisions?: AiSummaryDecisions
  claims: Claims
  fact_decisions?: FactDecisions
  invalidation_reason?: InvalidationReason
  source_excerpt: SourceExcerptV2
  status: Status
  summary: ContentSummaryCandidateV2
}
export interface ContentReviewDecisionV2 {
  command: Command
  created_at: CreatedAt
  decision_id: DecisionId
}
export interface ContentPreparationClaimV2 {
  basis: ClaimBasisV2
  claim_id: ClaimId
  evidence_locators: EvidenceLocators
}
export interface SourceExcerptV2 {
  claim_ids: ClaimIds
  evidence_locators: EvidenceLocators1
  text: Text
}
export interface ContentSummaryCandidateV2 {
  paragraphs: Paragraphs
  visible_character_count: VisibleCharacterCount
}
export interface ContentSummaryFactParagraphV2 {
  claim_ids: ClaimIds1
  judgment_type?: JudgmentType
  kind?: Kind
  section: Section
  text: Text1
}
export interface ContentSummaryJudgmentParagraphV2 {
  claim_ids?: ClaimIds2
  judgment_type: JudgmentType1
  kind?: Kind1
  section: Section1
  text: Text2
}
export interface SafeMetadata {
  [k: string]: any
}
