export type ClaimType = string
/**
 * @minItems 1
 */
export type EvidenceIds = [string, ...string[]]
export type Id = string
export type Label = string
export type Value = string

export interface ClaimView {
  claim_type: ClaimType
  evidence_ids: EvidenceIds
  id: Id
  label: Label
  value: Value
}
