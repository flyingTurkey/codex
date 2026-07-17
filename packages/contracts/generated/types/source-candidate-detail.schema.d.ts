export type AuthorizationBoundary = string
export type SourceCandidateAction = 'REQUEST_QUALIFICATION' | 'ENABLE' | 'DISMISS'
export type AvailableActions = SourceCandidateAction[]
export type BatchEnableEligible = boolean
export type CanonicalUrl = string
export type SourceContentDomain =
  | 'DIGITAL_TRANSFORMATION_CASE'
  | 'RESEARCH_PAPER'
  | 'SOFTWARE_PLATFORM'
  | 'IOT_EQUIPMENT'
  | 'LOW_ALTITUDE_EQUIPMENT'
  | 'AI_APPLICATION'
  | 'SAFETY_REGULATION'
  | 'STANDARD_GUIDANCE'
  | 'ACCIDENT_INVESTIGATION'
  | 'OFFICIAL_NOTICE'
  | 'PENALTY'
  | 'RECTIFICATION'
  | 'UNKNOWN'
export type ContentDomains = SourceContentDomain[]
export type DiscoveryChannel = 'DIRECTORY' | 'RSS' | 'SITEMAP' | 'OUTBOUND_LINK' | 'MANUAL' | 'BAIDU_SEARCH'
export type DiscoveryChannels = DiscoveryChannel[]
/**
 * @maxItems 100
 */
export type DiscoveryReferences = string[]
export type DismissedReason = string | null
export type EnabledSourceId = string | null
export type FirstDiscoveredAt = string
export type Id = string
export type SourceIndustry =
  | 'HIGHWAY'
  | 'BRIDGE'
  | 'TUNNEL'
  | 'RAILWAY'
  | 'RAIL_TRANSIT'
  | 'WATER_CONSERVANCY'
  | 'MUNICIPAL'
  | 'BUILDING'
  | 'ENERGY'
  | 'PORT_WATERWAY'
  | 'AIRPORT'
  | 'GENERAL_TRANSPORT'
  | 'UNKNOWN'
export type Industries = SourceIndustry[]
export type InstitutionName = string
export type LanguageTags = string[]
export type LastDiscoveredAt = string
export type BundleSha256 = string
export type CandidateId = string
export type Code = string
/**
 * @maxItems 50
 */
export type EvidenceRefs = string[]
export type QualificationCheckLevel = 'PASS' | 'WARN' | 'BLOCK'
export type Message = string
export type ObservedAt = string
/**
 * @maxItems 100
 */
export type Checks = QualificationCheckView[]
export type CreatedAt = string
/**
 * How qualification evidence may be captured, independent of display policy.
 */
export type EvidenceCapturePolicy = 'PRIVATE_RAW_ALLOWED' | 'TRANSIENT_METADATA_ONLY'
export type ExpiresAt = string
export type Id1 = string
export type MaterialFingerprint = string
/**
 * @maxItems 100
 */
export type ReasonCodes = string[]
export type RelevantItemCount = number
export type RuleVersion = string
export type RunId = string
export type SampledItemCount = number
export type StoragePolicy = 'RAW_EVIDENCE_ALLOWED' | 'METADATA_ONLY' | 'LINK_ONLY'
export type QualificationVerdict = 'QUALIFIED' | 'WARN_WAIVABLE' | 'BLOCKED'
export type OccurrenceCount = number
/**
 * @maxItems 50
 */
export type QualificationHistory = QualificationBundleView[]
export type SourceCandidateStatus =
  'DISCOVERED' | 'QUALIFYING' | 'READY_FOR_DECISION' | 'ENABLED' | 'DISMISSED' | 'BLOCKED' | 'STALE'

export interface SourceCandidateDetail {
  authorization_boundary: AuthorizationBoundary
  available_actions?: AvailableActions
  batch_enable_eligible?: BatchEnableEligible
  canonical_url: CanonicalUrl
  content_domains?: ContentDomains
  discovery_channels: DiscoveryChannels
  discovery_references?: DiscoveryReferences
  dismissed_reason?: DismissedReason
  enabled_source_id?: EnabledSourceId
  first_discovered_at: FirstDiscoveredAt
  id: Id
  industries?: Industries
  institution_name: InstitutionName
  language_tags?: LanguageTags
  last_discovered_at: LastDiscoveredAt
  latest_qualification?: QualificationBundleView | null
  occurrence_count: OccurrenceCount
  qualification_history?: QualificationHistory
  status: SourceCandidateStatus
}
export interface QualificationBundleView {
  bundle_sha256: BundleSha256
  candidate_id: CandidateId
  checks?: Checks
  created_at: CreatedAt
  evidence_capture_policy?: EvidenceCapturePolicy
  expires_at: ExpiresAt
  id: Id1
  material_fingerprint: MaterialFingerprint
  reason_codes?: ReasonCodes
  relevant_item_count: RelevantItemCount
  rule_version: RuleVersion
  run_id: RunId
  sampled_item_count: SampledItemCount
  storage_policy: StoragePolicy
  verdict: QualificationVerdict
}
export interface QualificationCheckView {
  code: Code
  evidence_refs?: EvidenceRefs
  level: QualificationCheckLevel
  message: Message
  observed_at: ObservedAt
}
