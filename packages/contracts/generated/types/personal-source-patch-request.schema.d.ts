export type DesiredEnabled = boolean | null
export type DisplayName = string | null

export interface PersonalSourcePatchRequest {
  desired_enabled?: DesiredEnabled
  display_name?: DisplayName
}
