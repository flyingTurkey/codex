import type { AppNavigationItem } from '@srbg/ui'

type Navigate = (to: string) => unknown

export function handleAppNavigation(
  item: Pick<AppNavigationItem, 'to'>,
  event: MouseEvent,
  navigate: Navigate,
): void {
  if (
    event.defaultPrevented
    || event.button !== 0
    || event.ctrlKey
    || event.metaKey
    || event.shiftKey
    || event.altKey
  ) {
    return
  }

  event.preventDefault()
  void navigate(item.to)
}

export const primaryNavigation = [
  {
    id: 'selected',
    label: '今日精选',
    to: '/',
    icon: 'Star',
    activePaths: ['/selected'],
  },
  { id: 'all', label: '全部动态', to: '/all', icon: 'List' },
  { id: 'search', label: '搜索', to: '/search', icon: 'Search' },
  { id: 'digital', label: '数字化', to: '/digital', icon: 'GraphUp' },
  { id: 'safety', label: '安全情报', to: '/safety', icon: 'ShieldCheck' },
  { id: 'hot', label: '行业热点', to: '/hot', icon: 'GraphUp' },
  { id: 'daily', label: '行业日报', to: '/daily', icon: 'Reports' },
  { id: 'saved', label: '收藏', to: '/saved', icon: 'Bookmark' },
] as const satisfies readonly AppNavigationItem[]

export const adminNavigation = [
  { id: 'operations', label: '运行中心', to: '/admin/operations', icon: 'RefreshDouble' },
  { id: 'ai', label: 'AI 模型配置', to: '/admin/ai', icon: 'Settings' },
  { id: 'quality', label: '质量看板', to: '/admin/quality', icon: 'Reports' },
  { id: 'sources', label: '我的来源', to: '/sources', icon: 'Settings' },
  { id: 'gold', label: '金标工作台', to: '/admin/gold', icon: 'ShieldCheck' },
] as const satisfies readonly AppNavigationItem[]

type NavigationRole
  = | 'auditor'
    | 'editor'
    | 'gold_annotator'
    | 'gold_arbitrator'
    | 'platform_admin'
    | 'reviewer'
    | 'source_admin'
    | 'viewer'

const adminNavigationRoles: Readonly<Record<(typeof adminNavigation)[number]['id'], readonly NavigationRole[]>> = {
  ai: ['platform_admin', 'auditor'],
  operations: ['platform_admin', 'auditor'],
  quality: ['platform_admin', 'auditor'],
  sources: ['source_admin', 'platform_admin', 'auditor'],
  gold: ['gold_annotator', 'gold_arbitrator', 'auditor'],
}

export function adminNavigationForRoles(roles: readonly string[]): readonly AppNavigationItem[] {
  const roleSet = new Set(roles)
  return adminNavigation.filter(item =>
    adminNavigationRoles[item.id].some(role => roleSet.has(role)),
  )
}
