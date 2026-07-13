import { mount } from '@vue/test-utils'

import { StatusBadge } from '../src/index'

describe('StatusBadge', () => {
  it.each([
    'healthy',
    'degraded',
    'verified',
    'pending',
    'vendor',
    'conflict',
    'withdrawn',
    'info',
  ] as const)('expresses the %s tone with both text and an icon', (tone) => {
    const wrapper = mount(StatusBadge, { props: { tone, label: `状态：${tone}` } })

    expect(wrapper.attributes('data-tone')).toBe(tone)
    expect(wrapper.text()).toContain(`状态：${tone}`)
    expect(wrapper.find('svg').exists()).toBe(true)
  })
})
