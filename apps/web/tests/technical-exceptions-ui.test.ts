import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const pagePath = resolve(process.cwd(), 'app/pages/technical-exceptions.vue')

describe('Owner technical exception workspace', () => {
  it('extends the shared exception workspace with bounded Safety decisions', () => {
    expect(existsSync(pagePath)).toBe(true)
    const source = readFileSync(pagePath, 'utf8')

    expect(source).toContain("import type { OwnerExceptionView }")
    expect(source).toContain("event_type: 'RETRY_REQUESTED'")
    expect(source).toContain("body: { desired_enabled: false }")
    expect(source).toContain("event_type: action")
    expect(source).toContain("'OWNER_ALLOWED'")
    expect(source).toContain("'OWNER_DENIED'")
    expect(source).toContain("item.overrideability !== 'HARD_BLOCK'")
    expect(source).toContain("kind: kindFilter.value")
    expect(source).toContain('安全硬阻断不可放行')
    expect(source).toContain('Idempotency-Key')
    expect(source).toContain('If-Match')
    expect(source).not.toContain('feed_suppression')
    expect(source).not.toContain('v-html')
  })
})
