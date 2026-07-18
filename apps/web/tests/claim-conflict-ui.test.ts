import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 claim review retirement', () => {
  it('removes the human claim conflict panel', () => {
    expect(existsSync(resolve(process.cwd(), 'app/components/ClaimConflictPanel.vue'))).toBe(false)
  })
})
