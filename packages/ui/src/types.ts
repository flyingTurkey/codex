import type { AppIconName } from './icons'

export interface AppNavigationItem {
  readonly id: string
  readonly label: string
  readonly to: string
  readonly icon: AppIconName
  readonly activePaths?: readonly string[]
}

export type StatusBadgeTone =
  | 'healthy'
  | 'degraded'
  | 'verified'
  | 'pending'
  | 'vendor'
  | 'conflict'
  | 'withdrawn'
  | 'info'
