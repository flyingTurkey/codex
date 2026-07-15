export type EvidenceId = string
export type Reason = string

export interface PublicationWithdrawalRequest {
  evidence_id: EvidenceId
  reason: Reason
}
