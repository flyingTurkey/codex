export type Eligible = boolean
export type EvaluatedAt = string
/**
 * @maxItems 30
 */
export type ReasonCodes = string[]
export type RuleVersion = string
export type SnapshotId = string
export type TotalScore = number
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
export type GeneratedAt = string
export type OverallConfidence = number
/**
 * @maxItems 8
 */
export type OverriddenFields = string[]
export type SourceProfileStatus = 'COMPLETE' | 'PARTIAL'
/**
 * Observed personal-source runtime state, independent from owner intent.
 */
export type PersonalSourceRuntimeState = 'PENDING_CONFIGURATION' | 'STOPPED' | 'RUNNING' | 'ERROR'
export type ActualRunning = boolean
/**
 * @minItems 1
 * @maxItems 32
 */
export type AllowedHosts = string[]
export type ConfigSha256 = string | null
export type ConsecutiveFailures = number
export type DiscoveryMethod = string
export type FailureReason1 = string | null
export type HealthObservationId = string | null
export type HealthObservedAt = string | null
export type PersonalStreamHealthReason =
  | 'DNS_FAILURE'
  | 'TLS_FAILURE'
  | 'TIMEOUT'
  | 'HTTP_401'
  | 'HTTP_403'
  | 'HTTP_404'
  | 'HTTP_429'
  | 'HTTP_5XX'
  | 'ROBOTS_BLOCKED'
  | 'LOGIN_REQUIRED'
  | 'CAPTCHA_DETECTED'
  | 'PAYWALL_DETECTED'
  | 'MIME_MISMATCH'
  | 'PARSE_FAILED'
  | 'ZERO_DISCOVERY_STREAK'
  | 'STRUCTURE_CHANGED'
  | 'REQUIRED_FIELDS_MISSING'
  | 'CONTENT_STALE'
  | 'BUDGET_EXHAUSTED'
  | 'CIRCUIT_OPEN'
export type PersonalStreamHealthStatus = 'UNKNOWN' | 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY'
export type Id2 = string
export type LastContentDiscoveredAt = string | null
export type LastSuccessfulFetchAt = string | null
export type NextSelfHealAt = string | null
export type NormalizedUrl = string
export type PersonalStreamRuntimeState =
  'STOPPED' | 'SCHEDULED' | 'CIRCUIT_OPEN' | 'HALF_OPEN' | 'BUDGET_EXHAUSTED' | 'INACCESSIBLE'
export type PersonalSourceStreamStatus = 'PROBING' | 'READY' | 'PROBE_FAILED'
export type PersonalSourceStreamType = 'UNKNOWN' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'LIST_DETAIL'
export type Streams = PersonalSourceStreamView[]
export type Url = string

export interface PersonalSourceView {
  auto_score_summary?: SourceAutoScoreSummaryView | null
  desired_enabled: DesiredEnabled
  display_name: DisplayName
  id: Id
  latest_probe_run?: StreamProbeRunView | null
  manual_disabled_at?: ManualDisabledAt
  normalized_origin?: NormalizedOrigin
  profile_summary?: SourceProfileSummaryView | null
  runtime_state: PersonalSourceRuntimeState
  streams?: Streams
  url: Url
}
export interface SourceAutoScoreSummaryView {
  eligible: Eligible
  evaluated_at: EvaluatedAt
  reason_codes: ReasonCodes
  rule_version: RuleVersion
  snapshot_id: SnapshotId
  total_score: TotalScore
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
export interface SourceProfileSummaryView {
  generated_at: GeneratedAt
  overall_confidence: OverallConfidence
  overridden_fields?: OverriddenFields
  status: SourceProfileStatus
}
export interface PersonalSourceStreamView {
  actual_running?: ActualRunning
  allowed_hosts: AllowedHosts
  config_sha256?: ConfigSha256
  consecutive_failures?: ConsecutiveFailures
  discovery_method: DiscoveryMethod
  failure_reason?: FailureReason1
  health_observation_id?: HealthObservationId
  health_observed_at?: HealthObservedAt
  health_reason?: PersonalStreamHealthReason | null
  health_status?: PersonalStreamHealthStatus
  id: Id2
  last_content_discovered_at?: LastContentDiscoveredAt
  last_successful_fetch_at?: LastSuccessfulFetchAt
  next_self_heal_at?: NextSelfHealAt
  normalized_url: NormalizedUrl
  runtime_state?: PersonalStreamRuntimeState
  status: PersonalSourceStreamStatus
  stream_type: PersonalSourceStreamType
}
