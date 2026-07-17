export type DurationMs = number | null
export type FailureCode = string | null
export type FailureReason = string | null
export type Id = string
export type PersonalSourceInputKind =
  'HOMEPAGE' | 'LIST_PAGE' | 'RSS_ATOM' | 'SITEMAP' | 'JSON_API' | 'DIRECT_PDF' | 'UNKNOWN'
export type RequestedUrl = string
export type PersonalSourceProbeStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'

export interface StreamProbeRunView {
  duration_ms?: DurationMs
  failure_code?: FailureCode
  failure_reason?: FailureReason
  id: Id
  input_kind: PersonalSourceInputKind
  requested_url: RequestedUrl
  status: PersonalSourceProbeStatus
}
