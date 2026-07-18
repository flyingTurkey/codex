export type AlgorithmVersion = string
export type CreatedAt = string
export type Id = string
export type InputFingerprintSha256 = string
export type AutomaticRelationshipKind =
  | 'DUPLICATE'
  | 'SAME_EVENT'
  | 'FOLLOW_UP_OF'
  | 'INVESTIGATES'
  | 'MODEL_ALIAS'
  | 'VERSION_SUCCESSOR'
  | 'TOPIC'
  | 'RELATED_CONTENT'
export type ModelVersion = string | null
/**
 * @maxItems 20
 */
export type ReasonCodes = string[]
export type RelationshipKey = string
export type ScoreBps = number
export type SourceItemId = string
export type Status = 'ACTIVE' | 'INVALIDATED' | 'WITHDRAWN' | 'SUPERSEDED'
export type TargetItemId = string

export interface AutomaticRelationshipView {
  algorithm_version: AlgorithmVersion
  created_at: CreatedAt
  id: Id
  input_fingerprint_sha256: InputFingerprintSha256
  kind: AutomaticRelationshipKind
  model_version?: ModelVersion
  reason_codes: ReasonCodes
  relationship_key: RelationshipKey
  score_bps: ScoreBps
  source_item_id: SourceItemId
  status: Status
  target_item_id: TargetItemId
}
