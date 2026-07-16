export type CompletedAt = string | null
export type ConnectorConfigVersionId = string
export type CreatedAt = string
export type Id = string
export type SourceTrialKind = 'FIXTURE_REPLAY' | 'LIVE_TRIAL'
export type PolicyVersionId = string
export type ParseFailedCount = number
export type RawCount = number
export type ReadyCount = number
export type ReadyRatioBps = number
export type RejectedRawAttemptCount = number
export type SecurityFailedCount = number
export type RequestedBy = string
export type SourceId = string
export type StartedAt = string | null
export type SourceTrialRunStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'

export interface SourceTrialRunView {
  completed_at?: CompletedAt
  connector_config_version_id: ConnectorConfigVersionId
  created_at: CreatedAt
  id: Id
  kind: SourceTrialKind
  policy_version_id: PolicyVersionId
  quality_summary?: SourceTrialQualitySummary | null
  requested_by: RequestedBy
  source_id: SourceId
  started_at?: StartedAt
  status: SourceTrialRunStatus
}
export interface SourceTrialQualitySummary {
  parse_failed_count: ParseFailedCount
  raw_count: RawCount
  ready_count: ReadyCount
  ready_ratio_bps: ReadyRatioBps
  rejected_raw_attempt_count: RejectedRawAttemptCount
  security_failed_count: SecurityFailedCount
}
