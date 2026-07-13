import { mount } from '@vue/test-utils'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

function getIntelligenceFeedPage(): Component | undefined {
  return componentModules['../app/components/IntelligenceFeedPage.vue']?.default
}

describe('IntelligenceFeedPage', () => {
  it('combines a page header, explicit status, and honest empty state', () => {
    const IntelligenceFeedPage = getIntelligenceFeedPage()
    expect(IntelligenceFeedPage, 'IntelligenceFeedPage.vue should exist').toBeDefined()
    if (!IntelligenceFeedPage) return
    const wrapper = mount(IntelligenceFeedPage, {
      props: {
        description: '只展示已接入的真实数据。',
        emptyDescription: '内容将在后续轮次接入。',
        emptyTitle: '业务数据尚未接入',
        statusLabel: '后续轮次接入',
        statusTone: 'info',
        title: '全部动态',
      },
    })

    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toBe('全部动态')
    expect(wrapper.text()).toContain('后续轮次接入')
    expect(wrapper.text()).toContain('业务数据尚未接入')
    expect(wrapper.find('main').exists()).toBe(false)
  })

  it('uses supplied content instead of rendering the default empty state', () => {
    const IntelligenceFeedPage = getIntelligenceFeedPage()
    expect(IntelligenceFeedPage, 'IntelligenceFeedPage.vue should exist').toBeDefined()
    if (!IntelligenceFeedPage) return
    const wrapper = mount(IntelligenceFeedPage, {
      props: {
        emptyTitle: '业务数据尚未接入',
        title: '数字化',
      },
      slots: {
        default: '<article data-testid="real-content">真实内容</article>',
      },
    })

    expect(wrapper.get('[data-testid="real-content"]').text()).toBe('真实内容')
    expect(wrapper.text()).not.toContain('业务数据尚未接入')
  })
})
