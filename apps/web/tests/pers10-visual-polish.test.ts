import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

describe('PERS-10 personal interface polish', () => {
  it('uses the approved typography and restrained motion system', () => {
    const css = source('app/assets/css/main.css')

    expect(css).toContain('text-rendering: optimizeLegibility')
    expect(css).toContain('font-synthesis: none')
    expect(css).toContain('var(--srbg-motion-base)')
    expect(css).toContain(':active:not(:disabled)')
    expect(css).toContain('prefers-reduced-motion: reduce')
  })

  it('gives the approved panes restrained token-based gradients', () => {
    const home = source('app/pages/index.vue')
    const sources = source('app/pages/sources.vue')
    const detail = source('app/pages/events/[id].vue')

    expect(home).toContain('linear-gradient(')
    expect(home).toContain('今日精选')
    expect(sources).toContain('source-overview')
    expect(sources).toContain('linear-gradient(')
    expect(sources).toContain('color: var(--color-ink-700);')
    expect(detail).toContain('reader-page__section')
    expect(detail).toContain('var(--color-surface)')
    expect(detail).toContain('reader-page__appendix')
  })
})
