export type Action = 'MERGE_ALIAS' | 'LINK_AS_NEW_VERSION' | 'KEEP_DISTINCT'
export type Reason = string

export interface ProductNormalizationDecisionRequest {
  action: Action
  reason: Reason
}
