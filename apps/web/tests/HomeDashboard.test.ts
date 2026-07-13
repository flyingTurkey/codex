import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeDashboard from '../app/components/HomeDashboard.vue'

describe('HomeDashboard', () => {
  it('shows the approved demo skeleton without invented business data', () => {
    const wrapper = mount(HomeDashboard, {
      props: {
        apiReachable: true,
        version: { api_version: 'v1', content_schema_version: '1.0.0' },
      },
    })

    expect(wrapper.get('h1').text()).toBe('今日情报概览')
    expect(wrapper.text()).toContain('四川路桥·智安情报')
    expect(wrapper.text()).toContain('演示环境')
    expect(wrapper.text()).toContain('数字化精选')
    expect(wrapper.text()).toContain('安全重点')
    expect(wrapper.findAll('[data-testid="metric"]')).toHaveLength(4)
    expect(
      wrapper.findAll('[data-testid="metric-value"]').map((metric) => metric.text()),
    ).toEqual(['--', '--', '--', '--'])
    expect(wrapper.text()).toContain('API v1 · Schema 1.0.0')
  })

  it('stays usable and reports a degraded API connection', () => {
    const wrapper = mount(HomeDashboard, {
      props: { apiReachable: false, version: null },
    })

    expect(wrapper.get('main').attributes('aria-labelledby')).toBe('page-title')
    expect(wrapper.text()).toContain('服务连接暂不可用')
    expect(wrapper.text()).not.toContain('API v1 · Schema 1.0.0')
  })
})
