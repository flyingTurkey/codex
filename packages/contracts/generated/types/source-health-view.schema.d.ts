export type Code = string
export type DetectedAt = string
export type Id = string
export type Severity = 'INFO' | 'WARNING' | 'CRITICAL'
export type SourceId = string
export type Status = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
export type Anomalies = SourceAnomalyView[]
export type DiscoveryStatus = string
export type FetchRunId = string
export type FreshnessStatus = string
export type ObservedAt = string
export type ParseStatus = string
export type QualityStatus = string
export type RuleVersion = string
export type SourceId1 = string
export type TransportStatus = string

export interface SourceHealthView {
  anomalies?: Anomalies
  discovery_status: DiscoveryStatus
  fetch_run_id: FetchRunId
  freshness_status: FreshnessStatus
  observed_at: ObservedAt
  parse_status: ParseStatus
  quality_status: QualityStatus
  rule_version: RuleVersion
  source_id: SourceId1
  transport_status: TransportStatus
}
export interface SourceAnomalyView {
  code: Code
  detected_at: DetectedAt
  id: Id
  severity: Severity
  source_id: SourceId
  status: Status
}
