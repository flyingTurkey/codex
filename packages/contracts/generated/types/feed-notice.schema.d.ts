export type Code = string
export type Level = 'info' | 'warning' | 'error'
export type Message = string

export interface FeedNotice {
  code: Code
  level: Level
  message: Message
}
