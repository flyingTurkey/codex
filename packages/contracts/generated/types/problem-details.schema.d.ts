export type Code = string | null
export type Detail = string | null
export type Instance = string | null
export type RequestId = string
export type Status = number
export type Title = string
export type Type = string

export interface ProblemDetails {
  code?: Code
  detail?: Detail
  instance?: Instance
  request_id: RequestId
  status: Status
  title: Title
  type?: Type
}
