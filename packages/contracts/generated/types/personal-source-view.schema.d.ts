export type DesiredEnabled = boolean
export type DisplayName = string
export type Id = string
export type DurationMs = number | null
export type FailureCode = string | null
export type FailureReason = string | null
export type Id1 = string
export type PersonalSourceInputKind =
  'HOMEPAGE' | 'LIST_PAGE' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'UNKNOWN'
export type RequestedUrl = string
export type PersonalSourceProbeStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
export type ManualDisabledAt = string | null
export type NormalizedOrigin = string | null
/**
 * Observed personal-source runtime state, independent from owner intent.
 */
export type PersonalSourceRuntimeState = 'PENDING_CONFIGURATION' | 'STOPPED' | 'RUNNING' | 'ERROR'
/**
 * @minItems 1
 * @maxItems 32
 */
export type AllowedHosts = string[]
export type ConfigSha256 = string | null
export type DiscoveryMethod = string
export type FailureReason1 = string | null
export type Id2 = string
export type NormalizedUrl = string
export type PersonalSourceStreamStatus = 'PROBING' | 'READY' | 'PROBE_FAILED'
export type PersonalSourceStreamType = 'UNKNOWN' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'LIST_DETAIL'
export type Streams = PersonalSourceStreamView[]
export type Url = string

export interface PersonalSourceView {
  desired_enabled: DesiredEnabled
  display_name: DisplayName
  id: Id
  latest_probe_run?: StreamProbeRunView | null
  manual_disabled_at?: ManualDisabledAt
  normalized_origin?: NormalizedOrigin
  runtime_state: PersonalSourceRuntimeState
  streams?: Streams
  url: Url
}
export interface StreamProbeRunView {
  duration_ms?: DurationMs
  failure_code?: FailureCode
  failure_reason?: FailureReason
  id: Id1
  input_kind: PersonalSourceInputKind
  requested_url: RequestedUrl
  status: PersonalSourceProbeStatus
}
export interface PersonalSourceStreamView {
  allowed_hosts: AllowedHosts
  config_sha256?: ConfigSha256
  discovery_method: DiscoveryMethod
  failure_reason?: FailureReason1
  id: Id2
  normalized_url: NormalizedUrl
  status: PersonalSourceStreamStatus
  stream_type: PersonalSourceStreamType
}
