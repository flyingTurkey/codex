import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import {
  designTokens,
  nuxtUiAppConfig,
  type DesignTokens,
  type TokenPath,
} from '../src/index'

const packageDirectory = process.cwd()
const tokenSource = resolve(packageDirectory, '../../docs/codex-kit/assets/ui/design_tokens.json')

describe('design tokens', () => {
  it('exports the canonical JSON as immutable, typed data', async () => {
    const canonicalTokens = JSON.parse(await readFile(tokenSource, 'utf8')) as unknown
    const typedTokens: DesignTokens = designTokens
    const knownPath: TokenPath = 'color.brand.600'

    expect(typedTokens).toEqual(canonicalTokens)
    expect(knownPath).toBe('color.brand.600')
    expect(Object.isFrozen(designTokens)).toBe(true)
  })

  it('maps Nuxt UI roles to the approved semantic palettes', () => {
    expect(nuxtUiAppConfig).toEqual({
      ui: {
        colors: {
          primary: 'brand',
          neutral: 'ink',
          success: 'verified',
          info: 'digital',
          warning: 'reviewPending',
          error: 'conflict',
        },
      },
    })
  })

  it('generates a Tailwind 4 theme whose missing shades alias canonical tokens', async () => {
    const theme = await readFile(`${packageDirectory}/src/generated/theme.css`, 'utf8')

    expect(theme).toContain('@theme {')
    expect(theme).toContain('--color-brand-600: var(--srbg-color-brand-600);')
    expect(theme).toContain('--color-brand-950: var(--srbg-color-brand-900);')
    expect(theme).toContain('--color-ink-200: var(--srbg-color-ink-100);')
    expect(theme).toContain('--color-reviewPending-600: var(--srbg-color-reviewPending-500);')
  })
})
