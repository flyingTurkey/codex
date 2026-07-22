import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const pagePath = resolve(process.cwd(), 'app/pages/technical-exceptions.vue')

describe('Owner technical exception workspace', () => {
  it('offers only retry and source-disable controls on the frozen technical contract', () => {
    expect(existsSync(pagePath)).toBe(true)
    const source = readFileSync(pagePath, 'utf8')

    expect(source).toContain("import type { OwnerExceptionView }")
    expect(source).toContain("event_type: 'RETRY_REQUESTED'")
    expect(source).toContain("body: { desired_enabled: false }")
    expect(source).toContain('Idempotency-Key')
    expect(source).toContain('If-Match')
    expect(source).not.toContain('OWNER_ALLOWED')
    expect(source).not.toContain('OWNER_DENIED')
    expect(source).not.toContain('feed_suppression')
  })
})
