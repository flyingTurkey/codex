import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 source registry UI', () => {
  it('exposes only the personal source route', () => {
    expect(existsSync(resolve(process.cwd(), 'app/pages/sources.vue'))).toBe(true)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/sources/index.vue'))).toBe(false)
  })
})
