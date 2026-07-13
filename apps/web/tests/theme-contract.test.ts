import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { nuxtUiAppConfig } from '@srbg/ui/app-config'

const webRoot = resolve(process.cwd())

function readWebFile(relativePath: string): string {
  return readFileSync(resolve(webRoot, relativePath), 'utf8')
}

describe('web theme integration', () => {
  it('declares the shared UI package and installs its generated theme', () => {
    const packageJson = JSON.parse(readWebFile('package.json')) as {
      dependencies: Record<string, string>
    }

    expect(packageJson.dependencies['@srbg/ui']).toBe('workspace:*')
    if (packageJson.dependencies['@srbg/ui'] !== 'workspace:*') return

    expect(readWebFile('app/assets/css/main.css')).toContain("@import '@srbg/ui/theme.css';")
    expect(readWebFile('app/app.config.ts')).toContain(
      "import { nuxtUiAppConfig } from '@srbg/ui/app-config'",
    )

    expect(nuxtUiAppConfig.ui.colors).toEqual({
      error: 'conflict',
      info: 'digital',
      neutral: 'ink',
      primary: 'brand',
      success: 'verified',
      warning: 'reviewPending',
    })
  })

  it('keeps readable UTF-8 product metadata in Nuxt configuration', () => {
    const source = readWebFile('nuxt.config.ts')

    expect(source).toContain('四川路桥行业数智与安全情报平台')
    expect(source).not.toMatch(/�|æƒ|æ™|è·¯æ¡¥/)
  })
})
