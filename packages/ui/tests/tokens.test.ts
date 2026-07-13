import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import {
  designTokens,
  nuxtUiAppConfig,
  type DesignTokens,
  type TokenPath,
} from '../src/index'
import { nuxtUiAppConfig as generatedNuxtUiAppConfig } from '../src/generated/design-tokens'

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

  it('exports the Nuxt UI app config through a Vue-free package subpath', async () => {
    const packageManifest = JSON.parse(
      await readFile(`${packageDirectory}/package.json`, 'utf8'),
    ) as { exports?: Record<string, unknown> }
    const appConfigExport = packageManifest.exports?.['./app-config']

    expect(appConfigExport).toEqual({
      types: './src/generated/design-tokens.ts',
      import: './src/generated/design-tokens.ts',
    })
    expect(JSON.stringify(appConfigExport)).not.toContain('src/index.ts')
    expect(generatedNuxtUiAppConfig).toEqual(nuxtUiAppConfig)
  })

  it('generates a Tailwind 4 theme whose missing shades alias canonical tokens', async () => {
    const theme = await readFile(`${packageDirectory}/src/generated/theme.css`, 'utf8')

    expect(theme).toContain('@theme {')
    expect(theme).toContain('--color-brand-600: var(--srbg-color-brand-600);')
    expect(theme).toContain('--color-brand-950: var(--srbg-color-brand-900);')
    expect(theme).toContain('--color-ink-200: var(--srbg-color-ink-100);')
    expect(theme).toContain('--color-reviewPending-600: var(--srbg-color-reviewPending-500);')
  })

  it('emits literal Tailwind breakpoint values that CSS tooling can use in media queries', async () => {
    const theme = await readFile(`${packageDirectory}/src/generated/theme.css`, 'utf8')

    for (const [name, value] of Object.entries(designTokens.breakpoint)) {
      expect(theme).toContain(`--breakpoint-${name}: ${value};`)
    }
    expect(theme).not.toMatch(/--breakpoint-[\w-]+:\s*var\(--srbg-breakpoint-/)
  })
})
