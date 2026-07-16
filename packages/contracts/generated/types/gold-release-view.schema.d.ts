export type FrozenAt = string
export type FrozenBy = string
export type Id = string
export type ManifestSha256 = string
export type Status = 'FROZEN'
export type Version = string

export interface GoldReleaseView {
  frozen_at: FrozenAt
  frozen_by: FrozenBy
  id: Id
  manifest_sha256: ManifestSha256
  status?: Status
  version: Version
}
