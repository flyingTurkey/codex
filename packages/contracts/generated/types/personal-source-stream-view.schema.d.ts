/**
 * @minItems 1
 * @maxItems 32
 */
export type AllowedHosts = string[]
export type ConfigSha256 = string | null
export type DiscoveryMethod = string
export type FailureReason = string | null
export type Id = string
export type NormalizedUrl = string
export type PersonalSourceStreamStatus = 'PROBING' | 'READY' | 'PROBE_FAILED'
export type PersonalSourceStreamType = 'UNKNOWN' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'LIST_DETAIL'

export interface PersonalSourceStreamView {
  allowed_hosts: AllowedHosts
  config_sha256?: ConfigSha256
  discovery_method: DiscoveryMethod
  failure_reason?: FailureReason
  id: Id
  normalized_url: NormalizedUrl
  status: PersonalSourceStreamStatus
  stream_type: PersonalSourceStreamType
}
