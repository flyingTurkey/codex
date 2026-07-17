export type AutomationEnabled = boolean | null

export interface DiscoverySettingPatchRequest {
  automation_enabled?: AutomationEnabled
}
