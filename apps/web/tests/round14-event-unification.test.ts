import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('round 14 Event identity switch', () => {
  it('keeps the legacy Item page as a 308-only compatibility route', () => {
    const source = readFileSync('app/pages/items/[id].vue', 'utf8')

    expect(source).toContain('redirectCode: 308')
    expect(source).toContain('rel="successor-version"')
    expect(source).not.toContain('ItemDetail')
    expect(source).not.toContain('IntelligenceCard')
  })

  it('links the shared feed card to the Event detail identity', () => {
    const source = readFileSync('app/components/IntelligenceCard.vue', 'utf8')

    expect(source).toContain('`/events/${item.id}`')
    expect(source).not.toContain('`/items/${item.id}`')
  })

  it('renders Event detail from the strict v2 reader and appendix endpoints', () => {
    const source = readFileSync('app/pages/events/[id].vue', 'utf8')

    expect(source).toContain('`/api/v2/events/${eventId}`')
    expect(source).toContain('`/api/v2/events/${eventId}/appendix`')
    expect(source).not.toContain('ItemDetail')
    expect(source).not.toContain('/content')
    expect(source).not.toContain('/source-comparison')
  })
})
