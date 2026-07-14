export type Action = 'APPROVE' | 'REJECT'
export type Reason = string

export interface ReviewDecisionRequest {
  action: Action
  reason: Reason
}
