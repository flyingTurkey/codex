export type Command =
  | 'CONFIRM_RELEVANCE'
  | 'EXCLUDE_RELEVANCE'
  | 'CORRECT_PRIMARY_TYPE'
  | 'CORRECT_FACETS'
  | 'ACCEPT_CLAIM'
  | 'REJECT_CLAIM'
  | 'REPLACE_CLAIM'
  | 'APPROVE_AI_SUMMARY'
  | 'REJECT_AI_SUMMARY'
  | 'REGENERATE_AI_SUMMARY'
  | 'DECIDE_RISK'
  | 'REEVALUATE'
export type ExpectedVersion = number
export type Reason = string

export interface ReviewDecisionCommandV2 {
  command: Command
  expected_version: ExpectedVersion
  payload?: Payload
  reason: Reason
}
export interface Payload {
  [k: string]: string | number | boolean | string[]
}
