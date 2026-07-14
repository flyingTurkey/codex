export type ClaimId = string | null
export type ConflictId = string | null
export type DisplayValue = '待核实'
export type EvidenceIds = string[]
export type SafetyCaseFactField =
  | 'OCCURRED_AT'
  | 'REGION'
  | 'PROJECT_NAME'
  | 'HAZARD_TYPE'
  | 'ENGINEERING_TYPE'
  | 'DEATH_COUNT'
  | 'INJURY_COUNT'
  | 'LOSS_AMOUNT_MINOR'
  | 'OFFICIAL_DIRECT_CAUSES'
  | 'RESPONSIBILITY_FINDINGS'
  | 'CORRECTIVE_ACTIONS'
export type Label = string
export type Reason = string
export type SourceItemId = string
export type Status = 'PENDING_REVIEW' | 'CONFLICTING'
export type Value = null

/**
 * Public-safe unresolved fact: candidate values are intentionally absent.
 */
export interface UnverifiedFact {
  claim_id?: ClaimId
  conflict_id?: ConflictId
  display_value?: DisplayValue
  evidence_ids?: EvidenceIds
  field: SafetyCaseFactField
  label: Label
  reason: Reason
  source_item_id: SourceItemId
  status: Status
  value?: Value
}
