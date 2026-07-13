import { mount } from '@vue/test-utils'

import { PageHeader } from '../src/index'

describe('PageHeader', () => {
  it('renders one page heading with readable context and action slots', () => {
    const wrapper = mount(PageHeader, {
      props: {
        title: '今日精选',
        eyebrow: '情报时间线',
        description: '更新时间：2026-07-13 09:00',
      },
      slots: { actions: '<button type="button">筛选</button>' },
    })

    expect(wrapper.get('h1').text()).toBe('今日精选')
    expect(wrapper.text()).toContain('情报时间线')
    expect(wrapper.text()).toContain('更新时间：2026-07-13 09:00')
    expect(wrapper.get('button').text()).toBe('筛选')
  })
})
