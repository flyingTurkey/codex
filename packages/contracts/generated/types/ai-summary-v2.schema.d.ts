export type Body = string | null
/**
 * @maxItems 100
 */
export type ClaimIds = string[]
export type GeneratedAt = string | null
/**
 * @maxItems 3
 */
export type JudgmentParagraphs = number[]
export type Model = string | null
/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds1 = string[]
export type JudgmentType = null
export type Kind = 'FACT'
export type Section = 'WHAT_HAPPENED'
export type Text = string
/**
 * @maxItems 0
 */
export type ClaimIds2 = string[]
export type JudgmentType1 = 'ENGINEERING_SIGNIFICANCE' | 'LIMITATION_AND_FOLLOW_UP'
export type Kind1 = 'JUDGMENT'
export type Section1 = 'ENGINEERING_IMPACT' | 'LIMITATIONS_AND_FOLLOW_UP'
export type Text1 = string
/**
 * @maxItems 12
 */
export type Paragraphs = (AiSummaryFactParagraphV2 | AiSummaryJudgmentParagraphV2)[]
export type AiSummaryStatusV2 =
  | 'NOT_GENERATED'
  | 'PROCESSING'
  | 'TEMPORARILY_UNAVAILABLE'
  | 'SCHEMA_REJECTED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'SUCCEEDED'
  | 'STALE'
export type StatusMessage = string

export interface AiSummaryV2 {
  body?: Body
  claim_ids?: ClaimIds
  generated_at?: GeneratedAt
  judgment_paragraphs?: JudgmentParagraphs
  model?: Model
  paragraphs?: Paragraphs
  status: AiSummaryStatusV2
  status_message?: StatusMessage
}
export interface AiSummaryFactParagraphV2 {
  claim_ids: ClaimIds1
  judgment_type?: JudgmentType
  kind?: Kind
  section: Section
  text: Text
}
export interface AiSummaryJudgmentParagraphV2 {
  claim_ids?: ClaimIds2
  judgment_type: JudgmentType1
  kind?: Kind1
  section: Section1
  text: Text1
}
