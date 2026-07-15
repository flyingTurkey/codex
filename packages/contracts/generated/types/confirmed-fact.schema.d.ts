export type ClaimId = string
/**
 * @minItems 1
 */
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
export type ReviewedAt = string
export type SourceItemId = string
export type Status = 'CONFIRMED'
export type Unit = string | null
export type Value = string | number | string[]

export interface ConfirmedFact {
  claim_id: ClaimId
  evidence_ids: EvidenceIds
  field: SafetyCaseFactField
  label: Label
  reviewed_at: ReviewedAt
  source_item_id: SourceItemId
  status?: Status
  unit?: Unit
  value: Value
}
