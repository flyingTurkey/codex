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
  { id: 'digital', label: '数字化', to: '/digital', icon: 'GraphUp' },
  { id: 'safety', label: '安全情报', to: '/safety', icon: 'ShieldCheck' },
  { id: 'daily', label: '行业日报', to: '/daily', icon: 'Reports' },
  { id: 'saved', label: '收藏', to: '/saved', icon: 'Bookmark' },
] as const satisfies readonly AppNavigationItem[]

export const adminNavigation = [
  { id: 'admin', label: '管理入口', to: '/admin', icon: 'Settings' },
] as const satisfies readonly AppNavigationItem[]
