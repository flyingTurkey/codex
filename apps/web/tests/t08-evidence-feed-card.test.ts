import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const components = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const baseItem = {
  activity_at: '2026-07-20T08:00:00Z',
  canonical_event_id: '019f7c00-0000-7000-8000-000000000821',
  content_type: 'SAFETY_CASE',
  detail_available: true,
  domain: 'SAFETY',
  event_status: 'ACTIVE',
  event_type: 'SAFETY_INCIDENT',
  event_version: 1,
  first_discovered_at: '2026-07-20T08:00:00Z',
  id: '019f7c00-0000-7000-8000-000000000821',
  is_saved: false,
  one_sentence_fact: '原文说明铁路隧道安全监测系统完成更新。',
  original_url: 'https://example.gov.cn/tunnel/1',
  publication_revision_id: null,
  review_status: 'APPROVED',
  source_name: '国家铁路局',
  source_published_at: null,
  title: '铁路隧道安全监测更新',
} as unknown as ItemSummary

describe('T08 evidence-first shared Feed/Card', () => {
  it('shows evidence and successful AI previews with an explicit low-weight search explanation', () => {
    const Card = components['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return
    const item = {
      ...baseItem,
      ai_summary_preview: {
        status: 'SUCCEEDED',
        status_message: 'AI 总结已按当前证据版本生成。',
        body: 'AI 总结仅解释当前已接受事实，并说明工程影响和待跟踪限制。',
      },
      search_explanation: {
        matched_evidence_fields: ['TITLE', 'SOURCE_EXCERPT'],
        ai_summary_assisted: true,
      },
    }

    const wrapper = mount(Card, { props: { item } })

    expect(wrapper.text()).toContain('原文摘录')
    expect(wrapper.text()).toContain(baseItem.one_sentence_fact)
    expect(wrapper.text()).toContain('AI 总结仅解释当前已接受事实')
    expect(wrapper.text()).toContain('证据字段命中：标题、原文摘录')
    expect(wrapper.text()).toContain('AI 总结低权重辅助召回')
  })

  it('keeps the evidence preview while showing the real non-success AI state', () => {
    const Card = components['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return
    const item = {
      ...baseItem,
      ai_summary_preview: {
        status: 'TEMPORARILY_UNAVAILABLE',
        status_message: 'AI 服务暂时不可用。系统会在受控上限内自动重试。',
        body: null,
      },
    }

    const wrapper = mount(Card, { props: { item } })

    expect(wrapper.text()).toContain(baseItem.one_sentence_fact)
    expect(wrapper.text()).toContain('AI 服务暂时不可用。系统会在受控上限内自动重试。')
  })

  it('does not render FULL-only search, excerpt, or AI fields for an R3 card', () => {
    const Card = components['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return
    const item = {
      ...baseItem,
      detail_available: false,
      one_sentence_fact: undefined,
      review_status: 'PENDING',
    }

    const wrapper = mount(Card, { props: { item } })

    expect(wrapper.text()).not.toContain('原文摘录')
    expect(wrapper.text()).not.toContain('AI 总结')
    expect(wrapper.text()).not.toContain('证据字段命中')
  })
})
