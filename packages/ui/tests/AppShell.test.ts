import { mount } from '@vue/test-utils'

import { AppShell, type AppNavigationItem } from '../src/index'

const primaryNavigation: readonly AppNavigationItem[] = [
  { id: 'selected', label: '今日精选', to: '/selected', icon: 'Star' },
]

const adminNavigation: readonly AppNavigationItem[] = [
  { id: 'settings', label: '管理入口', to: '/admin', icon: 'Settings' },
]

describe('AppShell', () => {
  it('provides one main landmark, a skip link, text branding, and permission-aware navigation', () => {
    const wrapper = mount(AppShell, {
      props: {
        brand: '四川路桥 · 智安情报',
        brandSubtitle: '行业数智与安全情报平台',
        primaryNavigation,
        adminNavigation,
        currentPath: '/selected',
        showAdmin: false,
      },
      slots: {
        default: '<p>主内容</p>',
        'sidebar-footer': '<span data-test="footer">查看账户</span>',
      },
    })

    expect(wrapper.get('.srbg-skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.findAll('main#main-content')).toHaveLength(1)
    expect(wrapper.text()).toContain('四川路桥 · 智安情报')
    expect(wrapper.text()).toContain('行业数智与安全情报平台')
    expect(wrapper.get('[data-test="footer"]').text()).toBe('查看账户')
    expect(wrapper.find('a[href="/admin"]').exists()).toBe(false)
  })
})
