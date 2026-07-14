export type DocumentVersionId = string
export type HeightMpt = number
export type PageCount = number
export type PageNumber = number
export type PreviewUrl = string
export type Rotation = 0 | 90 | 180 | 270
export type TextSource = 'NATIVE' | 'OCR' | 'MIXED'
export type WidthMpt = number

export interface DocumentPageView {
  document_version_id: DocumentVersionId
  height_mpt: HeightMpt
  page_count: PageCount
  page_number: PageNumber
  preview_url: PreviewUrl
  rotation: Rotation
  text_source: TextSource
  width_mpt: WidthMpt
}
