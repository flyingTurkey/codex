export type BaselineCommit = string
export type ConfigVersion = string
export type DatabaseRevision = string
export type DurationHours = 168
export type Environment = 'PREPRODUCTION'
export type GoldDefinitionVersion = string
export type MetricDefinitionVersion = string
export type Reason = string
export type RosterVersion = string
/**
 * @minItems 20
 * @maxItems 20
 */
export type SourceCodes = string[]

export interface PilotWindowCreateRequest {
  baseline_commit: BaselineCommit
  config_version: ConfigVersion
  database_revision: DatabaseRevision
  duration_hours?: DurationHours
  environment?: Environment
  gold_definition_version: GoldDefinitionVersion
  metric_definition_version: MetricDefinitionVersion
  reason: Reason
  roster_version: RosterVersion
  source_codes: SourceCodes
}
