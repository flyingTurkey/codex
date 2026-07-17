export type DesiredEnabled = boolean
export type DisplayName = string
export type Id = string
export type ManualDisabledAt = string | null
/**
 * Observed personal-source runtime state, independent from owner intent.
 */
export type PersonalSourceRuntimeState = 'PENDING_CONFIGURATION' | 'STOPPED' | 'RUNNING' | 'ERROR'
export type Url = string

export interface PersonalSourceView {
  desired_enabled: DesiredEnabled
  display_name: DisplayName
  id: Id
  manual_disabled_at?: ManualDisabledAt
  runtime_state: PersonalSourceRuntimeState
  url: Url
}
