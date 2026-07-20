import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ReaderAppendix from '../app/components/ReaderAppendix.vue'


const eventId = '019f7c00-0000-7000-8000-000000000311'

function emptyAppendix() {
  return {
    event_id: eventId,
    claims: [],
    evidence: [],
    automatic_results: [],
    relationships: [],
    automatic_relationships: [],
    corrections: [],
    review_context: null,
    review_href: '/review',
    content_summary: { total_items: 0, heavy_content: false, truncated_sections: [] },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ReaderAppendix', () => {
  it('is collapsed and unloaded until the first expansion, then reuses the result', async () => {
    let resolveRequest: ((value: ReturnType<typeof emptyAppendix>) => void) | undefined
    const request = vi.fn().mockImplementation(() => new Promise((resolve) => {
      resolveRequest = resolve
    }))
    vi.stubGlobal('$fetch', request)
    const wrapper = mount(ReaderAppendix, { props: { eventId } })

    expect(request).not.toHaveBeenCalled()
    expect(wrapper.get('button[aria-expanded="false"]').text()).toContain('展开')

    const expansion = wrapper.get('button').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('正在加载治理附录')
    resolveRequest?.(emptyAppendix())
    await expansion
    await flushPromises()
    expect(wrapper.text()).toContain('附录当前没有治理记录')
    expect(wrapper.text()).toContain('Accepted claims：0')
    expect(wrapper.text()).toContain('证据：0')

    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('keeps a failed request local to the appendix and supports an explicit retry', async () => {
    const request = vi.fn()
      .mockRejectedValueOnce(new Error('temporary failure'))
      .mockResolvedValueOnce(emptyAppendix())
    vi.stubGlobal('$fetch', request)
    const wrapper = mount(ReaderAppendix, { attachTo: document.body, props: { eventId } })

    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('治理附录加载失败')

    const retry = wrapper.get('[data-testid="appendix-retry"]')
    await retry.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('附录当前没有治理记录')
    expect(request).toHaveBeenCalledTimes(2)

    const toggle = wrapper.get('[data-testid="appendix-toggle"]')
    await toggle.trigger('click')
    expect(document.activeElement).toBe(toggle.element)
    wrapper.unmount()
  })

  it('separates evidence, automatic output, reviewed and automatic relations and corrections', async () => {
    const appendix = emptyAppendix()
    Object.assign(appendix, {
      claims: [{
        id: '019f7c00-0000-7000-8000-000000000312',
        claim_type: 'SAFETY_FACT', label: '阶段', value: '最终调查',
        evidence_ids: ['019f7c00-0000-7000-8000-000000000313'], decision_status: 'ACCEPTED',
      }],
      automatic_results: [{
        signal_id: '019f7c00-0000-7000-8000-000000000314', result_type: 'UNVERIFIED_AI',
        title: '模型候选', original_url: 'https://example.gov.cn/1', failure_reason_codes: [],
      }],
      relationships: [{
        id: '019f7c00-0000-7000-8000-000000000315', event_id: eventId,
        from_item_id: '019f7c00-0000-7000-8000-000000000316',
        to_item_id: '019f7c00-0000-7000-8000-000000000317', relation_type: 'INVESTIGATES',
        from_stage: 'FINAL_INVESTIGATION', to_stage: 'INITIAL_REPORT', reviewed_at: '2026-07-20T01:00:00Z',
      }],
      automatic_relationships: [{
        id: '019f7c00-0000-7000-8000-000000000318', relationship_key: 'follow-up',
        kind: 'FOLLOW_UP_OF', source_item_id: '019f7c00-0000-7000-8000-000000000316',
        target_item_id: '019f7c00-0000-7000-8000-000000000317', status: 'ACTIVE', score_bps: 9000,
        reason_codes: ['REPORT_STAGE_SEQUENCE'], algorithm_version: 'v1',
        input_fingerprint_sha256: 'a'.repeat(64), created_at: '2026-07-20T01:00:00Z',
      }],
      corrections: [{
        id: '019f7c00-0000-7000-8000-000000000319', kind: 'SOURCE_CORRECTED',
        description: '来源更正导致旧内容失效。', occurred_at: '2026-07-20T02:00:00Z',
        affects: ['SOURCE_EXCERPT', 'AI_SUMMARY'], document_version_id: null,
      }],
      review_context: {
        case_id: '019f7c00-0000-7000-8000-000000000320',
        href: '/review?case_id=019f7c00-0000-7000-8000-000000000320',
      },
      content_summary: { total_items: 101, heavy_content: true, truncated_sections: ['EVIDENCE'] },
    })
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue(appendix))
    const wrapper = mount(ReaderAppendix, { props: { eventId } })

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('AcceptedClaims 与证据')
    expect(wrapper.text()).toContain('自动处理结果（不是证据事实）')
    expect(wrapper.text()).toContain('已审核关系')
    expect(wrapper.text()).toContain('自动关系')
    expect(wrapper.text()).toContain('最终调查 → 初报')
    expect(wrapper.text()).toContain('结构化更正历史')
    expect(wrapper.text()).toContain('内容较多')
    expect(wrapper.get('a[href*="case_id="]').attributes('href')).toContain('000000000320')
    expect(wrapper.find('form').exists()).toBe(false)
  })
})
