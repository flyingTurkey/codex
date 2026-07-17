import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const appRoot = resolve(process.cwd(), 'app')

function source(path: string): string {
  return readFileSync(resolve(appRoot, path), 'utf8')
}

describe('source center UI', () => {
  it('adds source list, detail, coverage, and document metadata routes', () => {
    const routes = [
      'pages/admin/sources/index.vue',
      'pages/admin/sources/[id].vue',
      'pages/admin/sources/coverage.vue',
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
    expect(layout).toContain('adminNavigationForRoles')
    expect(layout).toContain('visibleAdminNavigation')
    expect(list).toContain('PageHeader')
    expect(list).toContain('StatusBadge')
    expect(list).toContain('ResponsiveDrawer')
    expect(list).toContain('EmptyState')
    expect(detail).toContain('PageHeader')
    expect(detail).toContain('StatusBadge')
    expect(detail).toContain('ResponsiveDrawer')
  })

  it('uses automation queues while retaining the read-compatible V2 detail route', () => {
    const list = source('pages/admin/sources/index.vue')
    const workspace = source('composables/useSourceCenterWorkspace.ts')
    const detail = source('pages/admin/sources/[id].vue')
    const document = source('pages/admin/documents/[id].vue')

    expect(list).toContain('useSourceCenterWorkspace')
    expect(workspace).toContain('/api/v1/admin/source-candidates')
    expect(workspace).toContain('/api/v1/admin/source-streams')
    expect(workspace).toContain('/api/v1/admin/source-attention')
    expect(detail).toContain('/policy-versions')
    expect(detail).toContain('/connector-config-versions/preview')
    expect(detail).toContain('/trial-runs')
    expect(detail).toContain('/lifecycle-events')
    expect(detail).toContain('/audit-events')
    expect(detail).not.toContain('/transitions')
    expect(detail).not.toContain('/enable')
    expect(detail).not.toContain('/disable')
    expect(document).toContain('/api/v1/admin/documents/')
  })
})
