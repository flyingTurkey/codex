import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 source approval workspace retirement', () => {
  it('removes candidate decisions and retains personal discovery controls', () => {
    expect(existsSync(resolve(process.cwd(), 'app/components/SourceCandidateDrawer.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/components/PersonalDiscoveryPanel.vue'))).toBe(true)
  })
})
