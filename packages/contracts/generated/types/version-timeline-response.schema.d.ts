export type ItemId = string
export type AcquiredAt = string
export type VersionChangeType =
  'INITIAL' | 'METADATA_ONLY' | 'CONTENT_UPDATE' | 'CORRECTION' | 'AMENDMENT' | 'REPLACEMENT' | 'WITHDRAWAL'
export type IsCurrent = boolean
export type Material = boolean
export type VersionProcessingState =
  'RECEIVED' | 'SECURITY_PASSED' | 'PARSING' | 'OCR_PENDING' | 'OCR_COMPLETE' | 'READY' | 'QUARANTINED' | 'FAILED'
export type VersionReviewState = 'DETECTED' | 'NO_REVIEW_REQUIRED' | 'RE_REVIEW_PENDING' | 'APPROVED' | 'REJECTED'
export type VersionId = string
export type VersionNumber = number
export type Versions = VersionTimelineEntry[]

export interface VersionTimelineResponse {
  item_id: ItemId
  versions: Versions
}
export interface VersionTimelineEntry {
  acquired_at: AcquiredAt
  change_type: VersionChangeType
  is_current: IsCurrent
  material: Material
  processing_state: VersionProcessingState
  review_state: VersionReviewState
  version_id: VersionId
  version_number: VersionNumber
}
