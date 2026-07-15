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
  { id: 'admin', label: '管理入口', to: '/admin/sources', icon: 'Settings' },
  { id: 'review', label: '审核工作台', to: '/admin/review', icon: 'ShieldCheck' },
  { id: 'clusters', label: '聚类工作台', to: '/admin/clusters', icon: 'List' },
] as const satisfies readonly AppNavigationItem[]
