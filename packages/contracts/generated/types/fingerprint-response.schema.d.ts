export type FeedGeneration = number
export type Fingerprint = string
export type GeneratedAt = string
export type HotTopicsGeneration = number
export type LatestDailyReportId = string | null
export type SearchGeneration = number

export interface FingerprintResponse {
  feed_generation: FeedGeneration
  fingerprint: Fingerprint
  generated_at: GeneratedAt
  hot_topics_generation: HotTopicsGeneration
  latest_daily_report_id?: LatestDailyReportId
  search_generation: SearchGeneration
}
