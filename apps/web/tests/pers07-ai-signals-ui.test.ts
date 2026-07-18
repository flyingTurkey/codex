import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const components = import.meta.glob('../app/components/*.vue', { eager: true }) as Record<
  string,
  { default?: object }
>

const base = {
  id: '019b0000-0000-7000-8000-000000000001',
  signal_id: '019b0000-0000-7000-8000-000000000002',
  publication_revision_id: null,
  domain: 'DIGITAL',
  content_type: 'DIGITAL_CASE',
  title: '桥梁智能巡检案例',
  source_name: '公开来源',
  source_published_at: '2026-07-18T00:00:00Z',
  first_discovered_at: '2026-07-18T00:00:00Z',
  activity_at: '2026-07-18T00:00:00Z',
  original_url: 'https://example.com/case',
  review_status: 'PENDING',
  event_type: 'DIGITAL_PROJECT',
  event_status: 'ACTIVE',
  canonical_event_id: '019b0000-0000-7000-8000-000000000001',
  event_version: 1,
}

describe('PERS-07 automatic AI signals', () => {
  it('renders unverified AI as a distinct machine-organized card with reasons', () => {
    const Card = components['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return
    const wrapper = mount(Card, {
      props: {
        item: {
          ...base,
          automatic_result_type: 'UNVERIFIED_AI',
          processing_failure_reasons: ['NUMBER_OR_DATE_CONFLICT'],
          ai_judgment: {
            why_worth_attention: '可能影响巡检效率',
            potential_industry_impacts: [],
            potential_engineering_scenarios: ['桥梁巡检'],
            current_limitations: ['数字待核实'],
            questions_to_verify: [],
            used_claim_ids: ['019b0000-0000-7000-8000-000000000101'],
          },
        },
      },
    })
    expect(wrapper.text()).toContain('未验证 AI')
    expect(wrapper.text()).toContain('机器整理 / 未人工复核')
    expect(wrapper.text()).toContain('数字或日期与证据冲突')
    expect(wrapper.get('article').classes()).toContain('is-unverified-ai')
  })

  it('never renders raw model text on processing-failure cards', () => {
    const Card = components['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return
    const wrapper = mount(Card, {
      props: {
        item: {
          ...base,
          automatic_result_type: 'AI_PROCESSING_FAILED',
          processing_failure_reasons: ['INVALID_JSON_OR_SCHEMA'],
        },
      },
    })
    expect(wrapper.text()).toContain('模型输出格式校验失败')
    expect(wrapper.text()).not.toContain('raw_output')
  })

  it('keys the shared timeline by signal id and keeps daily automatic', () => {
    const timeline = readFileSync(resolve(process.cwd(), 'app/components/TimelineFeed.vue'), 'utf8')
    const daily = readFileSync(resolve(process.cwd(), 'app/pages/daily.vue'), 'utf8')
    expect(timeline).toContain(':key="item.signal_id ?? item.id"')
    expect(daily).toContain('PublicationService 自动发布')
    expect(daily).not.toContain('/admin/daily/drafts')
  })
})
