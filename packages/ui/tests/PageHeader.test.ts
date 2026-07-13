import { mount } from '@vue/test-utils'

import { PageHeader } from '../src/index'

describe('PageHeader', () => {
  it('renders one page heading, Shanghai update time, status, and actions', () => {
    const updatedAt = '2026-07-13T01:00:00.000Z'
    const wrapper = mount(PageHeader, {
      props: {
        title: '今日精选',
        eyebrow: '情报时间线',
        description: '只展示经过门禁的真实情报。',
        updatedAt,
        updatedLabel: '更新时间',
      },
      slots: {
        actions: '<button type="button">筛选</button>',
        status: '<span data-test="status">工程基线可用</span>',
      },
    })

    expect(wrapper.get('h1').text()).toBe('今日精选')
    expect(wrapper.text()).toContain('情报时间线')
    expect(wrapper.text()).toContain('只展示经过门禁的真实情报。')
    expect(wrapper.get('[data-testid="page-updated-at"]').attributes('datetime')).toBe(updatedAt)
    expect(wrapper.get('[data-testid="page-updated-at"]').text()).toBe('2026-07-13 09:00')
    expect(wrapper.text()).toContain('更新时间')
    expect(wrapper.get('[aria-label="页面状态与更新时间"]').attributes('role')).toBe('group')
    expect(wrapper.get('[data-test="status"]').text()).toBe('工程基线可用')
    expect(wrapper.get('button').text()).toBe('筛选')
  })

  it('omits update metadata and status when neither is supplied', () => {
    const wrapper = mount(PageHeader, { props: { title: '安全情报' } })

    expect(wrapper.find('time').exists()).toBe(false)
    expect(wrapper.find('[aria-label="页面状态与更新时间"]').exists()).toBe(false)
  })
})
