export type VersionChangeType =
  'INITIAL' | 'METADATA_ONLY' | 'CONTENT_UPDATE' | 'CORRECTION' | 'AMENDMENT' | 'REPLACEMENT' | 'WITHDRAWAL'
export type ChangedTokenCount = number
export type ChangedTokenRatioBps = number
/**
 * @maxItems 20
 */
export type CriticalFields =
  | []
  | [CriticalFieldDiff]
  | [CriticalFieldDiff, CriticalFieldDiff]
  | [CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff]
  | [CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff]
  | [CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff]
  | [CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff, CriticalFieldDiff]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
  | [
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff,
      CriticalFieldDiff
    ]
export type After = string | null
export type Before = string | null
export type Field = 'document_number' | 'published_at' | 'effective_at' | 'legal_effect'
export type FromVersionId = string
export type ItemId = string
export type Material = boolean
export type Category = 'METADATA' | 'HEADER_FOOTER' | 'BODY' | 'CRITICAL_FIELD'
export type After1 = string | null
export type Before1 = string | null
export type Operation = 'INSERT' | 'DELETE' | 'REPLACE' | 'EQUAL'
/**
 * @maxItems 500
 */
export type Hunks = DiffHunk[]
export type PageNumber = number
/**
 * @maxItems 1000
 */
export type Pages = PageDiff[]
export type ToVersionId = string

export interface VersionDiffResponse {
  change_type: VersionChangeType
  changed_token_count: ChangedTokenCount
  changed_token_ratio_bps: ChangedTokenRatioBps
  critical_fields: CriticalFields
  from_version_id: FromVersionId
  item_id: ItemId
  material: Material
  pages: Pages
  to_version_id: ToVersionId
}
export interface CriticalFieldDiff {
  after?: After
  before?: Before
  field: Field
}
export interface PageDiff {
  category: Category
  hunks: Hunks
  page_number: PageNumber
}
export interface DiffHunk {
  after?: After1
  before?: Before1
  operation: Operation
}
