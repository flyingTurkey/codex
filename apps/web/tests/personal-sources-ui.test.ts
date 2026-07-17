import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('PERS-01 personal sources page', () => {
  const page = readFileSync(resolve(process.cwd(), 'app/pages/sources.vue'), 'utf8')
  const proxy = readFileSync(resolve(process.cwd(), 'server/api/v1/[...path].ts'), 'utf8')

  it('uses only the personal source API and separates intent from runtime', () => {
    expect(page).toContain('/api/v1/sources')
    expect(page).toContain('desired_enabled')
    expect(page).toContain('runtime_state')
    expect(page).toContain('待自动配置')
    expect(page).toContain('用户已启用')
    expect(page).toContain('当前正在运行')
  })

  it('does not expose legacy governance or future automation controls', () => {
    expect(page).not.toContain('/api/v1/admin/sources')
    expect(page).not.toContain('策略审批')
    expect(page).not.toContain('试运行批准')
    expect(page).not.toContain('治理元数据')
    expect(page).not.toContain('URL 探测')
    expect(page).not.toContain('自动画像')
  })

  it('forwards an ASCII-safe local Owner identity through HTTP headers', () => {
    expect(proxy).toContain("headers.set('x-srbg-local-user', 'Local Personal Owner')")
    expect(proxy).toContain("new Set(['owner', ...compatibleRoles])")
  })
})
