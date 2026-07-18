import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 scheduling UI retirement', () => {
  it('removes schedule repair and enterprise health pages', () => {
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/source-health.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/components/SourceLifecycleControls.vue'))).toBe(false)
  })
})
