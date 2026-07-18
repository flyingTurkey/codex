import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 source center retirement', () => {
  it('removes enterprise source governance pages and keeps personal sources', () => {
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/sources/index.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/sources.vue'))).toBe(true)
  })
})
