import { mount } from '@vue/test-utils'
import type { ProblemDetails } from '@srbg/contracts'

import { ProblemNotice } from '../src/index'

const problem: ProblemDetails = {
  type: 'https://srbg.example/problems/unavailable',
  title: '服务暂不可用',
  status: 503,
  detail: '情报源响应超时。',
  request_id: 'req-123',
}

describe('ProblemNotice', () => {
  it('directly renders Problem Details and offers an optional retry', async () => {
    const wrapper = mount(ProblemNotice, {
      props: { problem, retryLabel: '重试' },
    })

    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.get('h2').text()).toBe('服务暂不可用')
    expect(wrapper.text()).toContain('情报源响应超时。')
    expect(wrapper.text()).toContain('请求编号：req-123')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
