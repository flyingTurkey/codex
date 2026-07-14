import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const pending: ItemSummary = {
  activity_at: '2026-07-14T01:09:04Z',
  content_type: 'SAFETY_REGULATION',
  domain: 'SAFETY',
  first_discovered_at: '2026-07-14T01:09:04Z',
  id: '019b0000-0000-7000-8000-000000001001',
  original_url: 'https://www.mem.gov.cn/example.shtml',
  publication_revision_id: null,
  review_status: 'PENDING',
  source_name: '应急管理部',
  source_published_at: '2016-06-03T10:28:00Z',
  title: '生产安全事故应急预案管理办法',
}

describe('round 02 safety feed components', () => {
  it('ships one canonical set of the four feed components', () => {
    for (const name of [
      'TimelineFeed.vue',
      'IntelligenceCard.vue',
      'EvidenceDrawer.vue',
      'FilterPanel.vue',
    ]) {
      expect(componentModules[`../app/components/${name}`]?.default, `${name} should exist`).toBeDefined()
    }
  })

  it('renders an R3 pending card from whitelist fields without fabricated scores', () => {
    const Card = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return

    const wrapper = mount(Card, { props: { item: pending } })

    expect(wrapper.text()).toContain('待人工审核')
    expect(wrapper.text()).toContain('应急管理部')
    expect(wrapper.text()).not.toMatch(/评分|可信度|效力结论|摘要/)
    expect(wrapper.find('[data-testid="evidence-trigger"]').exists()).toBe(false)
  })

  it('renders evidence entry only after an immutable publication revision exists', () => {
    const Card = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(Card).toBeDefined()
    if (!Card) return

    const wrapper = mount(Card, {
      props: {
        item: {
          ...pending,
          evidence_count: 4,
          evidence_status: 'VERIFIED',
          publication_revision_id: '019b0000-0000-7000-8000-000000001002',
          publication_status: 'PUBLISHED',
          review_status: 'APPROVED',
          source_role: '官方一手来源',
          type_summary: {
            classification: 'DEPARTMENT_RULE',
            document_number: '国家安全生产监督管理总局令第88号',
            issuing_authority: '应急管理部',
            kind: 'SAFETY_REGULATION',
            regulation_status: 'UNKNOWN',
          },
        } satisfies ItemSummary,
      },
    })

    expect(wrapper.text()).toContain('已人工复核')
    expect(wrapper.text()).toContain('效力状态待核验')
    expect(wrapper.get('[data-testid="evidence-trigger"]').text()).toContain('4')
    expect(wrapper.text()).not.toContain('评分')
  })
})
