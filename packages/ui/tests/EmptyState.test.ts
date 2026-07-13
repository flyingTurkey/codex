import { mount } from '@vue/test-utils'

import { EmptyState } from '../src/index'

describe('EmptyState', () => {
  it('announces the empty result and exposes a recovery action', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '暂无情报', description: '调整筛选条件后重试。' },
      slots: { actions: '<button type="button">清除筛选</button>' },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.get('h2').text()).toBe('暂无情报')
    expect(wrapper.text()).toContain('调整筛选条件后重试。')
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.get('button').text()).toBe('清除筛选')
  })
})
