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
export type AiSummaryStatusV2 =
  | 'NOT_GENERATED'
  | 'PROCESSING'
  | 'TEMPORARILY_UNAVAILABLE'
  | 'SCHEMA_REJECTED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'SUCCEEDED'
  | 'STALE'

export interface AiSummaryV2 {
  body?: Body
  claim_ids?: ClaimIds
  generated_at?: GeneratedAt
  judgment_paragraphs?: JudgmentParagraphs
  model?: Model
  status: AiSummaryStatusV2
}
