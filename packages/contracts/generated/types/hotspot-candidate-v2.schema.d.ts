/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds1 = string[]
export type Text = string
/**
 * @minItems 1
 * @maxItems 5
 */
export type Reasons = HotspotCandidateReasonV2[]

export interface HotspotCandidateV2 {
  claim_ids: ClaimIds
  reasons: Reasons
}
export interface HotspotCandidateReasonV2 {
  claim_ids: ClaimIds1
  text: Text
}
