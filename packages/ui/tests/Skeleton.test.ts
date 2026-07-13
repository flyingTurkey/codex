import { mount } from '@vue/test-utils'

import { Skeleton } from '../src/index'

describe('Skeleton', () => {
  it('renders the requested loading placeholders with a readable label', () => {
    const wrapper = mount(Skeleton, {
      props: { lines: 3, label: '正在加载情报', animated: false },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.attributes('aria-label')).toBe('正在加载情报')
    expect(wrapper.findAll('.srbg-skeleton__line')).toHaveLength(3)
    expect(wrapper.classes()).not.toContain('srbg-skeleton--animated')
  })
})
