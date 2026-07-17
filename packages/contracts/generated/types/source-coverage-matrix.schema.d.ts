export type ActiveCount = number
export type CandidateCount = number
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
export type Gap = boolean
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
export type Language = string
export type Region = string
export type SourceType =
  | 'government'
  | 'standards'
  | 'journal'
  | 'research_institute'
  | 'association'
  | 'enterprise'
  | 'media'
  | 'academic_api'
  | 'academic_database'
export type TrialCount = number
export type Cells = SourceCoverageCell[]
export type GapCellCount = number
export type GeneratedAt = string

export interface SourceCoverageMatrix {
  cells: Cells
  gap_cell_count: GapCellCount
  generated_at: GeneratedAt
}
export interface SourceCoverageCell {
  active_count: ActiveCount
  candidate_count: CandidateCount
  content_domain: SourceContentDomain
  gap: Gap
  industry: SourceIndustry
  language: Language
  region: Region
  source_type: SourceType
  trial_count: TrialCount
}
