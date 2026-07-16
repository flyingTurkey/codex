export type ConnectorConfigVersionId = string
export type SourceTrialKind = 'FIXTURE_REPLAY' | 'LIVE_TRIAL'
export type PolicyVersionId = string
export type Reason = string

export interface SourceTrialRunRequest {
  connector_config_version_id: ConnectorConfigVersionId
  kind: SourceTrialKind
  policy_version_id: PolicyVersionId
  reason: Reason
}
