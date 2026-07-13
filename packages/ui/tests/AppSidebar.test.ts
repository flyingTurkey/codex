import { mount } from '@vue/test-utils'

import { AppSidebar, type AppNavigationItem } from '../src/index'

const primaryNavigation: readonly AppNavigationItem[] = [
  { id: 'selected', label: '今日精选', to: '/selected', icon: 'Star' },
  { id: 'digital', label: '数字化', to: '/digital', icon: 'GraphUp', activePaths: ['/digital/'] },
]

const adminNavigation: readonly AppNavigationItem[] = [
  { id: 'settings', label: '管理入口', to: '/admin', icon: 'Settings' },
]

describe('AppSidebar', () => {
  it('marks matching navigation and hides unauthorized administration', async () => {
    const wrapper = mount(AppSidebar, {
      props: {
        brand: '四川路桥 · 智安情报',
        primaryNavigation,
        adminNavigation,
        currentPath: '/digital/cases',
        showAdmin: false,
        responsiveCompact: true,
      },
      slots: { footer: '<span data-test="footer">测试用户</span>' },
    })

    expect(wrapper.get('nav').attributes('aria-label')).toBe('主导航')
    expect(wrapper.get('a[href="/digital"]').attributes('aria-current')).toBe('page')
    expect(wrapper.attributes('data-responsive-compact')).toBe('true')
    expect(wrapper.get('a[href="/digital"]').attributes('title')).toBe('数字化')
    expect(wrapper.find('a[href="/selected"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.find('a[href="/admin"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="footer"]').text()).toBe('测试用户')

    await wrapper.setProps({ showAdmin: true })
    expect(wrapper.get('a[href="/admin"]').text()).toContain('管理入口')
  })
})
