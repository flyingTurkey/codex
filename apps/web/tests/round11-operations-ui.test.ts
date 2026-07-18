import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-10 operations UI retirement', () => {
  it('removes the enterprise operations dashboard and routes', () => {
    expect(existsSync(resolve(process.cwd(), 'app/components/OperationsDashboard.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/operations.vue'))).toBe(false)
  })
})
