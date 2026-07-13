import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

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

    await nextTick()
    expect(wrapper.attributes('aria-busy')).toBe('false')
    expect(wrapper.get<HTMLButtonElement>('.srbg-app-shell__menu').element.disabled).toBe(false)
    expect(wrapper.getComponent(AppSidebar).props('responsiveCompact')).toBe(true)

    await wrapper.get('.srbg-app-shell__menu').trigger('click')
    const sidebars = wrapper.findAllComponents(AppSidebar)
    expect(sidebars).toHaveLength(2)
    expect(sidebars[0]?.props('responsiveCompact')).toBe(true)
    expect(sidebars[1]?.props('responsiveCompact')).toBe(false)
  })

  it('forwards desktop navigation with the original item and mouse event', async () => {
    const wrapper = mount(AppShell, {
      props: {
        brand: 'SRBG Intelligence',
        primaryNavigation,
        currentPath: '/selected',
      },
    })

    const desktopSidebar = wrapper.getComponent(AppSidebar)
    await desktopSidebar.get('a[href="/selected"]').trigger('click')

    const navigateEvent = wrapper.emitted('navigate')?.[0]
    const sidebarNavigateEvent = desktopSidebar.emitted('navigate')?.[0]
    expect(navigateEvent?.[0]).toBe(sidebarNavigateEvent?.[0])
    expect(navigateEvent?.[1]).toBe(sidebarNavigateEvent?.[1])
    expect(navigateEvent?.[1]).toBeInstanceOf(MouseEvent)
    expect((navigateEvent?.[1] as MouseEvent).defaultPrevented).toBe(false)
  })

  it('forwards drawer navigation with the mouse event and closes the drawer', async () => {
    const wrapper = mount(AppShell, {
      props: {
        brand: 'SRBG Intelligence',
        primaryNavigation,
        currentPath: '/selected',
      },
    })

    await nextTick()
    await wrapper.get('.srbg-app-shell__menu').trigger('click')
    const drawerSidebar = wrapper.findAllComponents(AppSidebar)[1]
    await drawerSidebar?.get('a[href="/selected"]').trigger('click')

    const navigateEvent = wrapper.emitted('navigate')?.[0]
    const sidebarNavigateEvent = drawerSidebar?.emitted('navigate')?.[0]
    expect(navigateEvent?.[0]).toBe(sidebarNavigateEvent?.[0])
    expect(navigateEvent?.[1]).toBe(sidebarNavigateEvent?.[1])
    expect(navigateEvent?.[1]).toBeInstanceOf(MouseEvent)
    expect((navigateEvent?.[1] as MouseEvent).defaultPrevented).toBe(false)
    expect(wrapper.find('.srbg-drawer').exists()).toBe(false)
  })

  it('uses the 200px derived sidebar contract only from 1280 through 1439 pixels', async () => {
    const source = await readFile(resolve(process.cwd(), 'src/components/AppShell.vue'), 'utf8')

    expect(source).toMatch(
      /@media \(min-width: 80rem\) and \(max-width: 89\.999rem\) \{[\s\S]*?grid-template-columns:\s*calc\(var\(--srbg-layout-sidebar\) - var\(--spacing-4\)\) minmax\(0, 1fr\);/,
    )
    expect(source).not.toContain(':deep(.srbg-sidebar')
  })
})
