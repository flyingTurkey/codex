import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const appRoot = resolve(process.cwd(), 'app')
const navigationModules = import.meta.glob<{
  adminNavigation: readonly { label: string }[]
  handleAppNavigation: (
    item: { to: string },
    event: MouseEvent,
    navigate: (to: string) => unknown,
  ) => void
  primaryNavigation: readonly { activePaths?: readonly string[]; label: string; to: string }[]
}>('../app/navigatio[n].ts', { eager: true })

function readAppFile(relativePath: string): string {
  return readFileSync(resolve(appRoot, relativePath), 'utf8')
}

function listProductionSources(directory = appRoot): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) return listProductionSources(path)
    return /\.(?:ts|vue)$/.test(entry.name) ? [path] : []
  })
}

const futureImplementationPattern =
  /\b(?:TimelineFeed|IntelligenceCard|PublicationService)\b|\b(?:interface|type|class)\s+(?:FeedPage|ItemSummary)\b/

describe('application shell contract', () => {
  it('keeps one UApp while delegating page chrome to the default Nuxt layout', () => {
    const source = readAppFile('app.vue')

    expect(source.match(/<UApp(?:\s|>)/g)).toHaveLength(1)
    expect(source).toContain('<NuxtLayout>')
    expect(source).toContain('<NuxtPage />')
  })

  it('defines the locked navigation and exposes management only to admin context', () => {
    const navigationPath = resolve(appRoot, 'navigation.ts')
    const layoutPath = resolve(appRoot, 'layouts/default.vue')

    expect(existsSync(navigationPath), 'navigation.ts should exist').toBe(true)
    expect(existsSync(layoutPath), 'layouts/default.vue should exist').toBe(true)
    if (!existsSync(navigationPath) || !existsSync(layoutPath)) return

    const navigation = navigationModules['../app/navigation.ts']
    expect(navigation, 'navigation.ts should be importable').toBeDefined()
    if (!navigation) return

    const { adminNavigation, primaryNavigation } = navigation
    expect(primaryNavigation.map((item) => [item.label, item.to])).toEqual([
      ['今日精选', '/'],
      ['全部动态', '/all'],
      ['搜索', '/search'],
      ['数字化', '/digital'],
      ['安全情报', '/safety'],
      ['行业热点', '/hot'],
      ['行业日报', '/daily'],
      ['收藏', '/saved'],
    ])
    expect(primaryNavigation[0]?.activePaths).toEqual(['/selected'])
    expect(adminNavigation.map((item) => item.label)).toEqual([
      '运行中心',
      'AI 模型配置',
      '质量看板',
      '我的来源',
      '金标工作台',
    ])
    expect(adminNavigation.find(item => item.id === 'sources')?.to).toBe('/sources')

    const layoutSource = readAppFile('layouts/default.vue')
    expect(layoutSource.match(/<AppShell(?:\s|>)/g)).toHaveLength(1)
    expect(layoutSource).toContain('adminNavigationForRoles')
    expect(layoutSource).toContain('visibleAdminNavigation')
    expect(layoutSource).toContain(':show-admin="showAdmin"')
    expect(layoutSource).toContain('@navigate="handleNavigation"')
  })

  it('uses client routing for an unmodified primary-button navigation event', () => {
    const navigation = navigationModules['../app/navigation.ts']
    const handleAppNavigation = navigation?.handleAppNavigation
    expect(handleAppNavigation, 'navigation.ts should export handleAppNavigation').toBeTypeOf('function')
    if (!handleAppNavigation) return

    const event = new MouseEvent('click', { button: 0, cancelable: true })
    const destinations: string[] = []

    handleAppNavigation({ to: '/digital' }, event, (to) => destinations.push(to))

    expect(event.defaultPrevented).toBe(true)
    expect(destinations).toEqual(['/digital'])
  })

  it('respects a navigation event already cancelled by an upstream listener', () => {
    const navigation = navigationModules['../app/navigation.ts']
    const handleAppNavigation = navigation?.handleAppNavigation
    expect(handleAppNavigation, 'navigation.ts should export handleAppNavigation').toBeTypeOf('function')
    if (!handleAppNavigation) return

    const event = new MouseEvent('click', { button: 0, cancelable: true })
    const destinations: string[] = []
    event.preventDefault()

    handleAppNavigation({ to: '/all' }, event, (to) => destinations.push(to))

    expect(event.defaultPrevented).toBe(true)
    expect(destinations).toEqual([])
  })

  it.each([
    ['middle button', { button: 1 }],
    ['control click', { button: 0, ctrlKey: true }],
    ['meta click', { button: 0, metaKey: true }],
    ['shift click', { button: 0, shiftKey: true }],
    ['alt click', { altKey: true, button: 0 }],
  ])('preserves native navigation for %s', (_label, init) => {
    const navigation = navigationModules['../app/navigation.ts']
    const handleAppNavigation = navigation?.handleAppNavigation
    expect(handleAppNavigation, 'navigation.ts should export handleAppNavigation').toBeTypeOf('function')
    if (!handleAppNavigation) return

    const event = new MouseEvent('click', { ...init, cancelable: true })
    const destinations: string[] = []

    handleAppNavigation({ to: '/safety' }, event, (to) => destinations.push(to))

    expect(event.defaultPrevented).toBe(false)
    expect(destinations).toEqual([])
  })

  it('keeps the real version request bounded and exposes only safe Problem Details', () => {
    const source = readAppFile('pages/index.vue')

    expect(source).toContain('/api/v1/version')
    expect(source).toMatch(/retry:\s*0/)
    expect(source).toMatch(/timeout:\s*2_000/)
    expect(source).toContain('ProblemDetails')
    expect(source).toContain('useState')
    expect(source).toContain('createUuidV7')
    expect(source).toContain("useState<string | null>('api-version-checked-at'")
    expect(source).toContain('new Date().toISOString()')
    expect(source).not.toContain('web-version-check')
    expect(source).not.toContain('error.value?.stack')
    expect(source).not.toContain('config.internalApiBase,')
  })

  it('prebundles the shared Iconoir entry before browser hydration', () => {
    const source = readFileSync(resolve(process.cwd(), 'nuxt.config.ts'), 'utf8')

    expect(source).toMatch(
      /vite:\s*\{[\s\S]*?optimizeDeps:\s*\{[\s\S]*?include:\s*\['iconoir-vue\/regular'\]/,
    )
  })

  it('reuses IntelligenceFeedPage for every feed route and honest placeholder route', () => {
    const directPages = ['selected.vue', 'all.vue', 'digital.vue', 'safety.vue', 'daily.vue', 'saved.vue']

    expect(readAppFile('components/HomeDashboard.vue')).toContain('<IntelligenceFeedPage')
    for (const page of directPages) {
      const path = resolve(appRoot, 'pages', page)
      expect(existsSync(path), `pages/${page} should exist`).toBe(true)
      if (existsSync(path)) expect(readAppFile(`pages/${page}`)).toContain('<IntelligenceFeedPage')
    }
  })

  it('introduces the frozen round 02 feed components without local contract redefinitions', () => {
    const violations = listProductionSources().flatMap((path) => {
      const source = readFileSync(path, 'utf8')
      return /\b(?:interface|type|class)\s+(?:FeedPage|ItemSummary|PublicationService)\b/.test(source)
        ? [path.slice(appRoot.length + 1)]
        : []
    })

    expect(violations).toEqual([])
    for (const component of [
      'TimelineFeed.vue',
      'IntelligenceCard.vue',
      'EvidenceDrawer.vue',
      'FilterPanel.vue',
    ]) {
      expect(existsSync(resolve(appRoot, 'components', component))).toBe(true)
    }
  })

  it('forbids only future implementations while allowing the shared page name', () => {
    expect(futureImplementationPattern.test('import IntelligenceFeedPage from "./IntelligenceFeedPage.vue"')).toBe(
      false,
    )
    expect(futureImplementationPattern.test('interface FeedPage {}')).toBe(true)
    expect(futureImplementationPattern.test('type ItemSummary = { id: string }')).toBe(true)
    expect(futureImplementationPattern.test('const card = new IntelligenceCard()')).toBe(true)
  })
})
