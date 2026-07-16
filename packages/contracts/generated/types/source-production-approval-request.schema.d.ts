export type ConnectorConfigVersionId = string
export type PolicyVersionId = string
export type Reason = string
export type TrialRunId = string

export interface SourceProductionApprovalRequest {
  connector_config_version_id: ConnectorConfigVersionId
  policy_version_id: PolicyVersionId
  reason: Reason
  trial_run_id: TrialRunId
}
