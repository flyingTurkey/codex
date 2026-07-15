export type Code = string
export type Status = 'PASS' | 'FAIL' | 'UNKNOWN'
export type Unit = 'count' | 'percent' | 'ms' | 'seconds' | 'minutes' | 'microusd'
export type Value = number
export type Metrics = MetricSample[]
export type ObservedAt = string

export interface OperationsOverview {
  metrics: Metrics
  observed_at: ObservedAt
}
export interface MetricSample {
  code: Code
  status: Status
  unit: Unit
  value: Value
}
