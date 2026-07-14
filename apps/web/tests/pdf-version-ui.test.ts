import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { describe, expect, it } from 'vitest'

import IntelligenceCard from '../app/components/IntelligenceCard.vue'
import PdfEvidenceViewer from '../app/components/PdfEvidenceViewer.vue'

const updatedItem: ItemSummary = {
  activity_at: '2026-07-14T01:09:04Z',
  content_type: 'SAFETY_REGULATION',
  document_states: ['UPDATED', 'RE_REVIEW_PENDING', 'SOURCE_UNAVAILABLE'],
  domain: 'SAFETY',
  first_discovered_at: '2026-07-14T01:09:04Z',
  has_version_history: true,
  id: '019b0000-0000-7000-8000-000000011001',
  original_url: 'https://www.mem.gov.cn/test-only/rule.pdf',
  publication_revision_id: null,
  review_status: 'PENDING',
  source_name: '应急管理部',
  source_published_at: '2026-07-01T00:00:00Z',
  title: '测试专用桥梁施工安全规定',
}

describe('round 03 PDF and version UI', () => {
  it('extends the canonical intelligence card with explicit document states', () => {
    const wrapper = mount(IntelligenceCard, { props: { item: updatedItem } })

    expect(wrapper.text()).toContain('已更新')
    expect(wrapper.text()).toContain('待复核')
    expect(wrapper.text()).toContain('原文失效')
    expect(wrapper.text()).not.toContain('官方已核验')
  })

  it('renders a bounded server PNG with page controls and coordinate highlight', async () => {
    const wrapper = mount(PdfEvidenceViewer, {
      props: {
        evidence: [
          {
            claim_ids: ['019b0000-0000-7000-8000-000000011002'],
            document_version_id: '019b0000-0000-7000-8000-000000011003',
            excerpt: '实施日期：2026-08-01',
            excerpt_sha256: 'a'.repeat(64),
            id: '019b0000-0000-7000-8000-000000011004',
            locator: {
              bbox: { x0: 100000, x1: 300000, y0: 200000, y1: 240000 },
              block_id: '019b0000-0000-7000-8000-000000011005',
              page_number: 2,
              type: 'PDF_TEXT',
            },
            original_url: 'https://www.mem.gov.cn/test-only/rule.pdf',
          },
        ],
        page: {
          document_version_id: '019b0000-0000-7000-8000-000000011003',
          height_mpt: 842000,
          page_count: 3,
          page_number: 2,
          preview_url: '/api/v1/document-versions/019b0000-0000-7000-8000-000000011003/pages/2/preview',
          rotation: 0,
          text_source: 'NATIVE',
          width_mpt: 595000,
        },
      },
    })

    expect(wrapper.get('img').attributes('src')).toContain('/pages/2/preview')
    expect(wrapper.get('[data-testid="pdf-highlight"]').attributes('style')).toContain('left: 16.8067%')
    await wrapper.get('[aria-label="下一页"]').trigger('click')
    expect(wrapper.emitted('page')?.[0]).toEqual([3])
  })
})
