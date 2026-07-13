import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'

import { AppShell, AppSidebar, type AppNavigationItem } from '../src/index'

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

  it('delegates responsive compact behavior only to its desktop sidebar', async () => {
    const wrapper = mount(AppShell, {
      props: {
        brand: '四川路桥 · 智安情报',
        primaryNavigation,
        adminNavigation,
        currentPath: '/selected',
      },
    })

    expect(wrapper.getComponent(AppSidebar).props('responsiveCompact')).toBe(true)

    await wrapper.get('.srbg-app-shell__menu').trigger('click')
    const sidebars = wrapper.findAllComponents(AppSidebar)
    expect(sidebars).toHaveLength(2)
    expect(sidebars[0]?.props('responsiveCompact')).toBe(true)
    expect(sidebars[1]?.props('responsiveCompact')).toBe(false)
  })

  it('uses the 200px derived sidebar contract only from 1280 through 1439 pixels', async () => {
    const source = await readFile(resolve(process.cwd(), 'src/components/AppShell.vue'), 'utf8')

    expect(source).toMatch(
      /@media \(min-width: 80rem\) and \(max-width: 89\.999rem\) \{[\s\S]*?grid-template-columns:\s*calc\(var\(--srbg-layout-sidebar\) - var\(--spacing-4\)\) minmax\(0, 1fr\);/,
    )
    expect(source).not.toContain(':deep(.srbg-sidebar')
  })
})
