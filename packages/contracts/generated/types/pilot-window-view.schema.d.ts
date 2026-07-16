export type BaselineCommit = string
/**
 * @maxItems 100
 */
export type BlockerCodes = string[]
export type ConfigVersion = string
export type DatabaseRevision = string
export type DurationHours = 168
export type EndsAt = string | null
export type Environment = 'PREPRODUCTION'
export type GoldDefinitionVersion = string
export type Id = string
export type MetricDefinitionVersion = string
export type PreparedAt = string
export type RosterVersion = string
export type SourceCount = number
export type StartedAt = string | null
export type PilotWindowState = 'PREPARING' | 'READY' | 'RUNNING' | 'COMPLETED' | 'BLOCKED'
export type Version = number

export interface PilotWindowView {
  baseline_commit: BaselineCommit
  blocker_codes?: BlockerCodes
  config_version: ConfigVersion
  database_revision: DatabaseRevision
  duration_hours: DurationHours
  ends_at?: EndsAt
  environment: Environment
  gold_definition_version: GoldDefinitionVersion
  id: Id
  metric_definition_version: MetricDefinitionVersion
  prepared_at: PreparedAt
  roster_version: RosterVersion
  source_count: SourceCount
  started_at?: StartedAt
  state: PilotWindowState
  version: Version
}
