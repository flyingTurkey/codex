import type { ProblemDetails } from '@srbg/contracts'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeDashboard from '../app/components/HomeDashboard.vue'

const unavailableProblem: ProblemDetails = {
  detail: '版本服务暂时无法响应，请稍后重试。',
  request_id: 'web-version-check',
  status: 503,
  title: '工程基线连接暂不可用',
  type: 'about:blank',
}

describe('HomeDashboard', () => {
  it('shows the verified engineering baseline and one honest empty state', () => {
    const wrapper = mount(HomeDashboard, {
      props: {
        problem: null,
        version: { api_version: 'v1', content_schema_version: '1.0.0' },
      },
    })

    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toBe('今日精选')
    expect(wrapper.text()).toContain('工程基线可用')
    expect(wrapper.text()).toContain('API v1 · Schema 1.0.0')
    expect(wrapper.text()).toContain('业务数据尚未接入')
    expect(wrapper.text()).toContain('后续轮次')
    expect(wrapper.findAll('[data-testid="metric"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('今日新增')
    expect(wrapper.text()).not.toContain('评分')
    expect(wrapper.find('main').exists()).toBe(false)
  })

  it('renders Problem Details without hiding the real empty state', () => {
    const wrapper = mount(HomeDashboard, {
      props: { problem: unavailableProblem, version: null },
    })

    expect(wrapper.get('[role="alert"]').text()).toContain(unavailableProblem.title)
    expect(wrapper.get('[role="alert"]').text()).toContain(unavailableProblem.detail)
    expect(wrapper.get('[role="alert"]').text()).toContain(unavailableProblem.request_id)
    expect(wrapper.text()).toContain('业务数据尚未接入')
    expect(wrapper.text()).not.toContain('API v1 · Schema 1.0.0')
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.find('main').exists()).toBe(false)
  })
})
