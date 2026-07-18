export type ActualRunning = boolean
/**
 * @minItems 1
 * @maxItems 32
 */
export type AllowedHosts = string[]
export type ConfigSha256 = string | null
export type ConsecutiveFailures = number
export type DiscoveryMethod = string
export type FailureReason = string | null
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
export type Id = string
export type LastContentDiscoveredAt = string | null
export type LastSuccessfulFetchAt = string | null
export type NextSelfHealAt = string | null
export type NormalizedUrl = string
export type PersonalStreamRuntimeState =
  'STOPPED' | 'SCHEDULED' | 'CIRCUIT_OPEN' | 'HALF_OPEN' | 'BUDGET_EXHAUSTED' | 'INACCESSIBLE'
export type PersonalSourceStreamStatus = 'PROBING' | 'READY' | 'PROBE_FAILED'
export type PersonalSourceStreamType = 'UNKNOWN' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'LIST_DETAIL'

export interface PersonalSourceStreamView {
  actual_running?: ActualRunning
  allowed_hosts: AllowedHosts
  config_sha256?: ConfigSha256
  consecutive_failures?: ConsecutiveFailures
  discovery_method: DiscoveryMethod
  failure_reason?: FailureReason
  health_observation_id?: HealthObservationId
  health_observed_at?: HealthObservedAt
  health_reason?: PersonalStreamHealthReason | null
  health_status?: PersonalStreamHealthStatus
  id: Id
  last_content_discovered_at?: LastContentDiscoveredAt
  last_successful_fetch_at?: LastSuccessfulFetchAt
  next_self_heal_at?: NextSelfHealAt
  normalized_url: NormalizedUrl
  runtime_state?: PersonalStreamRuntimeState
  status: PersonalSourceStreamStatus
  stream_type: PersonalSourceStreamType
}
