/**
 * @maxItems 30
 */
export type ApplicationScenarios = string[]
export type CurrentVersion = string | null
/**
 * @maxItems 20
 */
export type DeploymentModes = string[]
/**
 * @minItems 1
 */
export type EvidenceIds = string[]
export type ItemId = string
export type Title = string
/**
 * @maxItems 50
 */
export type EngineeringCases = ProductEngineeringCase[]
export type ProductEvidenceLevel =
  | 'VENDOR_CLAIM_ONLY'
  | 'PROJECT_EVIDENCE'
  | 'RESEARCH_EVIDENCE'
  | 'INDEPENDENT_VALIDATION'
  | 'OFFICIAL_CERTIFICATION'
  | 'UNKNOWN'
/**
 * @maxItems 30
 */
export type Interfaces = string[]
/**
 * @maxItems 50
 */
export type Limitations = string[]
export type LowAltitudeNotice = '产品发布不代表空域、适航、飞手和项目许可。' | null
export type Id = string
export type Name = string
export type ProductPermitStatus = 'VERIFIED' | 'NOT_REQUIRED' | 'UNKNOWN'
export type ProcurementNotice = '仅供技术调研，不构成采购建议'
export type ProductKind = string
export type Attribution = string
export type ClaimId = string
/**
 * @minItems 1
 */
export type EvidenceIds1 = string[]
export type IndependentEvidenceIds = string[]
export type ProductCapabilityKind = 'PROMOTIONAL_CLAIM' | 'VERIFIED_CAPABILITY'
export type Statement = string
export type PromotionalClaims = ProductCapability[]
export type VerifiedCapabilities = ProductCapability[]
/**
 * @maxItems 100
 */
export type VersionHistory = string[]

export interface TechnologyProductDetail {
  application_scenarios: ApplicationScenarios
  current_version?: CurrentVersion
  deployment_modes: DeploymentModes
  engineering_cases: EngineeringCases
  evidence_level: ProductEvidenceLevel
  interfaces: Interfaces
  limitations: Limitations
  low_altitude_notice?: LowAltitudeNotice
  model?: ProductEntity | null
  permit_status: ProductPermitStatus
  procurement_notice: ProcurementNotice
  product: ProductEntity
  product_kind: ProductKind
  promotional_claims: PromotionalClaims
  vendor: ProductEntity
  verified_capabilities: VerifiedCapabilities
  version_history: VersionHistory
}
export interface ProductEngineeringCase {
  evidence_ids: EvidenceIds
  item_id: ItemId
  title: Title
}
export interface ProductEntity {
  id: Id
  name: Name
}
export interface ProductCapability {
  attribution: Attribution
  claim_id: ClaimId
  evidence_ids: EvidenceIds1
  independent_evidence_ids?: IndependentEvidenceIds
  kind: ProductCapabilityKind
  statement: Statement
}
