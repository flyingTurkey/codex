export type Service = 'api'
export type Status = 'ok'
export type Timestamp = string

export interface LivenessResponse {
  service?: Service
  status?: Status
  timestamp: Timestamp
}
