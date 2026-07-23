import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const read = (path: string) => readFileSync(path, 'utf8')

describe('Owner Feed suppression UI', () => {
  it('offers an accessible confirmed Event action on the shared Feed surface', () => {
    const card = read('app/components/IntelligenceCard.vue')
    const timeline = read('app/components/TimelineFeed.vue')
    const feed = read('app/components/IntelligenceFeedPage.vue')

    expect(card).toContain("suppress: [itemId: string]")
    expect(card).toContain('data-testid="suppress-event"')
    expect(timeline).toContain('@suppress="')
    expect(feed).toContain('/api/v2/owner/suppressions')
    expect(feed).toContain("'Idempotency-Key': createUuidV7()")
    expect(feed).toContain('feedback_reason: \'OWNER_PREFERENCE\'')
    expect(feed).toContain('role="status"')
    expect(feed).toContain('role="alert"')
  })

  it('offers the same server command from the unified Event reader', () => {
    const reader = read('app/pages/events/[id].vue')

    expect(reader).toContain('data-testid="suppress-event"')
    expect(reader).toContain("scope: 'EVENT'")
    expect(reader).toContain("'Idempotency-Key': createUuidV7()")
    expect(reader).toContain('role="alertdialog"')
    expect(reader).toContain('role="status"')
  })

  it('provides a separate control plane that revokes append-only rules with If-Match', () => {
    const page = read('app/pages/feed-suppressions.vue')
    const navigation = read('app/navigation.ts')
    const proxy = read('server/api/v2/[...path].ts')

    expect(page).toContain('/api/v2/owner/suppressions')
    expect(page).toContain("action: 'REVOKE'")
    expect(page).toContain("'If-Match': `\"${item.id}\"`")
    expect(page).toContain("'Idempotency-Key': createUuidV7()")
    expect(navigation).toContain("to: '/feed-suppressions'")
    expect(page).not.toContain('SAFETY_DENIAL')
    expect(page).toContain("data?.detail?.code === 'SUPPRESSION_CONFLICT'")
    expect(page).toContain('隐藏规则已发生变化，请刷新列表后再操作。')
    expect(proxy).toContain('`${config.internalApiBase}/api/v2/${path}${search}`')
  })
})
