import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 pilot UI retirement', () => {
  it('removes pilot and gold workspaces', () => {
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/pilot.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/gold.vue'))).toBe(false)
  })
})
