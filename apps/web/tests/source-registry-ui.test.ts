import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const appRoot = resolve(process.cwd(), 'app')

function source(path: string): string {
  return readFileSync(resolve(appRoot, path), 'utf8')
}

describe('round 01 source registry UI', () => {
  it('adds source list, detail, and document metadata routes', () => {
    const routes = [
      'pages/admin/sources/index.vue',
      'pages/admin/sources/[id].vue',
      'pages/admin/documents/[id].vue',
    ]

    for (const route of routes) {
      expect(existsSync(resolve(appRoot, route)), route).toBe(true)
    }
  })

  it('reuses the locked shell and UI primitives for the management workflow', () => {
    const layout = source('layouts/default.vue')
    const list = source('pages/admin/sources/index.vue')
    const detail = source('pages/admin/sources/[id].vue')

    expect(layout).toContain('<AppShell')
    expect(layout).toContain("route.path.startsWith('/admin')")
    expect(list).toContain('PageHeader')
    expect(list).toContain('StatusBadge')
    expect(list).toContain('ResponsiveDrawer')
    expect(list).toContain('EmptyState')
    expect(detail).toContain('PageHeader')
    expect(detail).toContain('StatusBadge')
    expect(detail).toContain('ResponsiveDrawer')
  })

  it('uses the real admin APIs for default-denied registration and fixture upload', () => {
    const list = source('pages/admin/sources/index.vue')
    const detail = source('pages/admin/sources/[id].vue')
    const document = source('pages/admin/documents/[id].vue')

    expect(list).toContain('/api/v1/admin/sources')
    expect(detail).toContain('/policy')
    expect(detail).toContain('/transitions')
    expect(detail).toContain('/fixture')
    expect(detail).toContain('/onboarding-records')
    expect(document).toContain('/api/v1/admin/documents/')
  })
})
