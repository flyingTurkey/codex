export type CaseId = string
export type CreatedAt = string
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
  created_at: CreatedAt
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
export interface SafeMetadata {
  [k: string]: any
}
