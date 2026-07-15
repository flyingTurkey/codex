import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const paperItem = {
  activity_at: '2026-07-15T04:00:00Z',
  content_type: 'JOURNAL_PAPER',
  domain: 'DIGITAL',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-15T04:05:00Z',
  id: '019b0000-0000-7000-8000-000000006201',
  original_url: 'https://doi.org/10.1000/bridge.2025.1',
  publication_revision_id: '019b0000-0000-7000-8000-000000006202',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: 'OpenAlex',
  source_published_at: '2025-07-01T00:00:00Z',
  source_role: '开放学术元数据',
  title: '桥梁数字孪生研究',
  type_summary: {
    access_level: 'METADATA_ONLY',
    ai_short_comment: null,
    doi: '10.1000/bridge.2025.1',
    engineering_domains: ['BRIDGE'],
    journal: '中国公路学报',
    kind: 'JOURNAL_PAPER',
    maturity_level: 'LAB_PROTOTYPE',
    open_status: 'CLOSED',
    paper_type: 'ARTICLE',
    relation_status: 'RETRACTED',
    technology_tags: ['DIGITAL_TWIN'],
    year: 2025,
  },
} as unknown as ItemSummary

describe('round 06 journal paper UI', () => {
  it('renders paper metadata, access boundary, maturity and retraction in shared card', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item: paperItem } })

    expect(wrapper.text()).toContain('期刊论文')
    expect(wrapper.text()).toContain('10.1000/bridge.2025.1')
    expect(wrapper.text()).toContain('中国公路学报')
    expect(wrapper.text()).toContain('仅题录')
    expect(wrapper.text()).toContain('实验室原型')
    expect(wrapper.text()).toContain('已撤稿')
    expect(wrapper.text()).toContain('研究结果不代表已完成工程生产应用')
    expect(wrapper.text()).not.toContain('可信度')
  })

  it('adds paper tab and configuration-driven paper filters to the existing digital page', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/digital.vue'), 'utf8')
    const panel = readFileSync(resolve(process.cwd(), 'app/components/FilterPanel.vue'), 'utf8')

    expect(page).toContain("value: 'JOURNAL_PAPER'")
    expect(page).toContain('show-paper-filters')
    expect(panel).toContain('论文类型')
    expect(panel).toContain('技术标签')
    expect(panel).toContain('开放状态')
    expect(panel).toContain('发表年份')
  })

  it('keeps metadata, abstract, fulltext, citation and similar papers explicit on shared detail', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/items/[id].vue'), 'utf8')

    expect(page).toContain('元数据可见')
    expect(page).toContain('许可不明确，未收录摘要')
    expect(page).toContain('平台未保存全文')
    expect(page).toContain('复制 GB/T 7714')
    expect(page).toContain('导出 RIS')
    expect(page).toContain('导出 BibTeX')
    expect(page).toContain('相似论文')
  })
})
