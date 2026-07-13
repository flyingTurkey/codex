export type DisplayName = string
export type LocalIdentity = boolean
export type UserRole = 'viewer' | 'editor' | 'reviewer' | 'source_admin' | 'platform_admin' | 'auditor'
export type Roles = UserRole[]
export type UserId = string

export interface MeResponse {
  display_name: DisplayName
  local_identity: LocalIdentity
  roles: Roles
  user_id: UserId
}
