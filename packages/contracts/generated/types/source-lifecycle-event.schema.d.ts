export type SourceLifecycleAction =
  | 'SUBMIT_COMPLIANCE'
  | 'START_FIXTURE_TRIAL'
  | 'START_LIVE_TRIAL'
  | 'APPROVE_PRODUCTION'
  | 'PAUSE'
  | 'RESUME'
  | 'RETIRE'
export type ActorId = string | null
export type CreatedAt = string
/**
 * Authoritative V2 source lifecycle computed by the server.
 */
export type SourceLifecycleState = 'CANDIDATE' | 'COMPLIANCE_REVIEW' | 'TRIAL' | 'ACTIVE' | 'PAUSED' | 'RETIRED'
export type GovernanceDecisionId = string | null
export type Id = string
export type MigrationRuleVersion = string | null
export type PolicyVersionId = string | null
export type Reason = string
export type ReasonCode = string
export type SourceId = string

export interface SourceLifecycleEventView {
  action: SourceLifecycleAction | null
  actor_id: ActorId
  created_at: CreatedAt
  from_state: SourceLifecycleState | null
  governance_decision_id?: GovernanceDecisionId
  id: Id
  migration_rule_version?: MigrationRuleVersion
  policy_version_id?: PolicyVersionId
  reason: Reason
  reason_code: ReasonCode
  source_id: SourceId
  to_state: SourceLifecycleState
}
