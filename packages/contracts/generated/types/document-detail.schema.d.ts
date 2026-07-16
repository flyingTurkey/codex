export type CanonicalUrl = string
export type AcquiredAt = string
export type ContentHash = string
export type Id = string
export type OriginalFilename = string
export type Title = string | null
export type VersionNumber = number
export type DocumentKind = 'HTML' | 'PDF' | 'DISCOVERY_XML' | 'DISCOVERY_JSON'
export type FirstDiscoveredAt = string
export type Id1 = string
export type ByteSize = number
export type DetectedMime = 'text/html' | 'application/pdf' | 'application/xml' | 'application/json'
export type Id2 = string
export type ScanStatus = 'CLEAN' | 'REJECTED'
export type Sha256 = string
export type SourceId = string
export type SourceName = string

export interface DocumentDetail {
  canonical_url: CanonicalUrl
  current_version: DocumentVersionSummary
  document_kind: DocumentKind
  first_discovered_at: FirstDiscoveredAt
  id: Id1
  raw_object: RawObjectSummary
  source_id: SourceId
  source_name: SourceName
}
export interface DocumentVersionSummary {
  acquired_at: AcquiredAt
  content_hash: ContentHash
  id: Id
  original_filename: OriginalFilename
  title: Title
  version_number: VersionNumber
}
export interface RawObjectSummary {
  byte_size: ByteSize
  detected_mime: DetectedMime
  id: Id2
  scan_status: ScanStatus
  sha256: Sha256
}
