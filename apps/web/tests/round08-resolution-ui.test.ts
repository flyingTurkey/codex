import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const item = {
  activity_at: '2026-07-15T03:00:00Z',
  content_type: 'DIGITAL_CASE',
  domain: 'DIGITAL',
  first_discovered_at: '2026-07-15T03:00:00Z',
  id: '019b0000-0000-7000-8000-000000008001',
  original_url: 'https://example.com/case',
  publication_revision_id: '019b0000-0000-7000-8000-000000008002',
  review_status: 'APPROVED',
  scores: {
    relevance: {
      calculated_at: '2026-07-15T03:00:00Z',
      dimension: 'RELEVANCE',
      features: [{ code: 'DOMAIN', explanation: '工程领域匹配', label: '专业匹配', points: 70 }],
      overridden: false,
      raw_score: 88,
      rule_version: 'scoring-v1.0.0',
      score: 88,
    },
    authority: {
      calculated_at: '2026-07-15T03:00:00Z',
      dimension: 'AUTHORITY',
      features: [{ code: 'SOURCE_LEVEL', explanation: '省级官方来源', label: '来源等级', points: 95 }],
      overridden: false,
      raw_score: 95,
      rule_version: 'scoring-v1.0.0',
      score: 95,
    },
  },
  source_name: '四川省交通运输厅',
  source_published_at: '2026-07-15T03:00:00Z',
  title: '桥梁数字化案例',
} as unknown as ItemSummary

describe('round 08 explainable resolution UI', () => {
  it('shows one named relevance summary and opens all available dimensions', async () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item } })
    expect(wrapper.findAll('[data-testid="score-summary"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="score-summary"]').text()).toContain('相关度 88')
    expect(wrapper.text()).not.toContain('可信度')

    await wrapper.get('[data-testid="score-summary"]').trigger('click')
    expect(wrapper.get('[data-testid="score-breakdown"]').text()).toContain('权威 95')
    expect(wrapper.get('[data-testid="score-breakdown"]').text()).toContain('scoring-v1.0.0')
  })

  it('adds hot topics, source comparison and a governed cluster workbench in the shared shell', () => {
    const navigation = readFileSync(resolve(process.cwd(), 'app/navigation.ts'), 'utf8')
    const hotPage = readFileSync(resolve(process.cwd(), 'app/pages/hot.vue'), 'utf8')
    const eventPage = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')
    const workbench = readFileSync(resolve(process.cwd(), 'app/pages/admin/clusters.vue'), 'utf8')

    expect(navigation).toContain("to: '/hot'")
    expect(navigation).toContain("to: '/admin/clusters'")
    expect(hotPage).toContain('/api/v1/hot-topics')
    expect(eventPage).toContain('SourceComparison')
    expect(workbench).toContain('/api/v1/admin/clustering-workbench')
    expect(workbench).toContain('只读历史')
    expect(workbench).toContain('PERS-08')
    expect(workbench).not.toContain('/decisions')
  })
})
