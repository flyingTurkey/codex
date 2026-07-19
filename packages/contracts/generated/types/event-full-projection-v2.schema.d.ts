export type Body = string | null
/**
 * @maxItems 100
 */
export type ClaimIds = string[]
export type GeneratedAt = string | null
/**
 * @maxItems 3
 */
export type JudgmentParagraphs = number[]
export type Model = string | null
export type AiSummaryStatusV2 =
  | 'NOT_GENERATED'
  | 'PROCESSING'
  | 'TEMPORARILY_UNAVAILABLE'
  | 'SCHEMA_REJECTED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'SUCCEEDED'
  | 'STALE'
export type DownloadUrl = string | null
export type MediaId = string | null
export type Name = string
export type RedistributionAllowed = boolean
export type SourceUrl = string
/**
 * @maxItems 100
 */
export type Attachments = AttachmentViewV2[]
export type ClaimBasisV2 =
  | 'MANUFACTURER_CLAIM'
  | 'RESEARCH_CONCLUSION'
  | 'PROJECT_FIRST_PARTY_RECORD'
  | 'INDEPENDENT_VERIFICATION'
  | 'AUTHORITY_FINDING'
/**
 * @minItems 1
 * @maxItems 5
 */
export type ClaimBasis = ClaimBasisV2[]
export type CorrectionAlert = string | null
export type EventId = string
export type PrimaryIntelligenceType = 'DIGITAL_TRANSFORMATION' | 'SAFETY_INTELLIGENCE' | 'INDUSTRY_UPDATE'
/**
 * @maxItems 2
 */
export type CrossTypeTags = PrimaryIntelligenceType[]
export type EngineeringObject =
  | 'HIGHWAY'
  | 'RAILWAY'
  | 'BRIDGE'
  | 'TUNNEL'
  | 'BUILDING'
  | 'MINING'
  | 'MUNICIPAL'
  | 'WATER_CONSERVANCY'
  | 'PORT_WATERWAY'
  | 'AIRPORT'
  | 'ENERGY'
/**
 * @minItems 1
 * @maxItems 11
 */
export type EngineeringObjects = EngineeringObject[]
export type EquipmentFacet = 'CONSTRUCTION_MACHINERY'
/**
 * @maxItems 1
 */
export type EquipmentDomains = EquipmentFacet[]
export type SpecialtyFacet = 'TUNNEL_GAS_MONITORING'
/**
 * @maxItems 1
 */
export type Specialties = SpecialtyFacet[]
export type FirstDiscoveredAt = string
export type IndependentSourceCount = number
/**
 * @minItems 1
 * @maxItems 5
 */
export type Reasons = string[]
export type Trigger = 'MULTI_SOURCE_7D' | 'AUTHORITY_SCORE'
export type MediaId1 = string
export type Name1 = string
export type PreviewUrl = string | null
export type RightsBasis = 'PUBLIC_DOMAIN' | 'EXPLICIT_LICENSE' | 'SOURCE_AUTHORIZED' | 'OWNER_OWNED'
/**
 * @maxItems 50
 */
export type Media = MediaViewV2[]
export type OriginalUrl = string
export type ProjectionKind = 'FULL'
export type Name2 = string
export type Official = boolean
/**
 * @minItems 1
 * @maxItems 100
 */
export type ClaimIds1 = string[]
/**
 * @minItems 1
 * @maxItems 100
 */
export type EvidenceLocators = string[]
export type Text = string
export type SourcePublishedAt = string | null
export type Title = string

export interface EventFullProjectionV2 {
  ai_summary: AiSummaryV2
  attachments?: Attachments
  claim_basis: ClaimBasis
  correction_alert?: CorrectionAlert
  event_id: EventId
  facets: IntelligenceFacetsV2
  first_discovered_at: FirstDiscoveredAt
  hotspot?: HotspotReasonV2 | null
  media?: Media
  original_url: OriginalUrl
  primary_type: PrimaryIntelligenceType
  projection_kind?: ProjectionKind
  source: SourceAttributionV2
  source_excerpt: SourceExcerptV2
  source_published_at: SourcePublishedAt
  title: Title
}
export interface AiSummaryV2 {
  body?: Body
  claim_ids?: ClaimIds
  generated_at?: GeneratedAt
  judgment_paragraphs?: JudgmentParagraphs
  model?: Model
  status: AiSummaryStatusV2
}
export interface AttachmentViewV2 {
  download_url?: DownloadUrl
  media_id?: MediaId
  name: Name
  redistribution_allowed: RedistributionAllowed
  source_url: SourceUrl
}
export interface IntelligenceFacetsV2 {
  cross_type_tags?: CrossTypeTags
  engineering_objects: EngineeringObjects
  equipment_domains?: EquipmentDomains
  specialties?: Specialties
}
export interface HotspotReasonV2 {
  independent_source_count: IndependentSourceCount
  reasons: Reasons
  trigger: Trigger
}
export interface MediaViewV2 {
  media_id: MediaId1
  name: Name1
  preview_url?: PreviewUrl
  rights_basis: RightsBasis
}
export interface SourceAttributionV2 {
  name: Name2
  official: Official
}
export interface SourceExcerptV2 {
  claim_ids: ClaimIds1
  evidence_locators: EvidenceLocators
  text: Text
}
