import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ReaderActions from '../app/components/ReaderActions.vue'

describe('ReaderActions', () => {
  it('renders each original and attachment action exactly once', () => {
    const wrapper = mount(ReaderActions, {
      props: {
        originalUrl: 'https://example.com/original',
        attachments: [
          {
            media_id: '019f7c00-0000-7000-8000-000000000021',
            name: '许可附件.pdf',
            download_url: '/api/v2/media/019f7c00-0000-7000-8000-000000000021/download',
            source_url: 'https://example.com/licensed.pdf',
            redistribution_allowed: true,
          },
          {
            media_id: null,
            name: '仅原站材料.pdf',
            download_url: null,
            source_url: 'https://example.com/source-only.pdf',
            redistribution_allowed: false,
          },
        ],
      },
    })

    expect(wrapper.findAll('a[href="https://example.com/original"]')).toHaveLength(1)
    expect(wrapper.findAll('a[href^="/api/v2/media/"]')).toHaveLength(1)
    expect(wrapper.findAll('a[href="https://example.com/source-only.pdf"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('下载许可附件.pdf')
    expect(wrapper.text()).toContain('在原站查看仅原站材料.pdf')
  })
})
