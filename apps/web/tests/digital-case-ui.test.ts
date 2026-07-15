import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const digitalItem = {
  activity_at: '2026-07-14T04:00:00Z',
  content_type: 'DIGITAL_CASE',
  domain: 'DIGITAL',
  evidence_count: 2,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-14T04:05:00Z',
  id: '019b0000-0000-7000-8000-000000005201',
  original_url: 'https://www.shudaojt.com/example.pdf',
  publication_revision_id: '019b0000-0000-7000-8000-000000005202',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '蜀道集团',
  source_published_at: '2022-03-10T00:00:00Z',
  source_role: '企业自述',
  scores: {
    relevance: {
      calculated_at: '2026-07-14T04:05:00Z',
      dimension: 'RELEVANCE',
      features: [
        { code: 'ENGINEERING_DOMAIN', explanation: '工程专业匹配', label: '工程专业匹配', points: 70 },
        { code: 'SICHUAN', explanation: '四川实施', label: '四川实施', points: 20 },
        { code: 'SRBG_DIRECT', explanation: '四川路桥直接关系', label: '四川路桥直接关系', points: 10 },
      ],
      overridden: false,
      raw_score: 100,
      rule_version: 'scoring-v1.0.0',
      score: 100,
    },
  },
  title: '智慧梁厂2.0',
  type_summary: {
    ai_short_comment: null,
    application_scenarios: ['QUALITY_CONTROL', 'PROGRESS_CONTROL'],
    deployment_scale: '沿江高速 5913 片 T 梁、98 座桥梁',
    kind: 'DIGITAL_CASE',
    maturity_level: 'SINGLE_PROJECT_PRODUCTION',
    publisher_claim_label: '发布方声明/未独立验证',
    relevance: {
      factors: [
        { code: 'ENGINEERING_DOMAIN', label: '工程专业匹配', points: 70 },
        { code: 'SICHUAN', label: '四川实施', points: 20 },
        { code: 'SRBG_DIRECT', label: '四川路桥直接关系', points: 10 },
      ],
      rule_version: 'relevance-v1.0.0',
      score: 100,
    },
    source_nature: 'ENTERPRISE_SELF_REPORT',
    srbg_relationship: '四川路桥所属单位实施项目',
  },
} as unknown as ItemSummary

describe('round 05 digital case UI', () => {
  it('extends the shared IntelligenceCard with attributed outcomes and explainable relevance', async () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item: digitalItem } })

    expect(wrapper.text()).toContain('数字化案例')
    expect(wrapper.text()).toContain('单项目生产应用')
    expect(wrapper.text()).toContain('企业自述')
    expect(wrapper.text()).toContain('发布方声明/未独立验证')
    expect(wrapper.text()).toContain('四川路桥所属单位实施项目')
    expect(wrapper.get('[data-testid="score-summary"]').text()).toContain('相关度 100')
    await wrapper.get('[data-testid="score-summary"]').trigger('click')
    expect(wrapper.get('[data-testid="score-breakdown"]').text()).toContain('scoring-v1.0.0')
    expect(wrapper.text()).not.toContain('可信度')
    expect(wrapper.text()).not.toContain('官方已核验')
    expect(wrapper.text()).not.toContain('AI短评')
  })

  it('offers controlled digital filters without creating a parallel feed', async () => {
    const FilterPanel = componentModules['../app/components/FilterPanel.vue']?.default
    expect(FilterPanel).toBeDefined()
    if (!FilterPanel) return

    const wrapper = mount(FilterPanel, {
      props: {
        contentType: 'DIGITAL_CASE',
        contentTypeOptions: [{ label: '案例', value: 'DIGITAL_CASE' }],
        engineeringDomain: 'all',
        maturity: 'all',
        scenario: 'all',
        showDigitalFilters: true,
        showDomain: false,
        sourceNature: 'all',
      },
    })

    expect(wrapper.get('[aria-label="工程专业"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="应用场景"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="成熟度"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="来源性质"]').exists()).toBe(true)
    await wrapper.get('[aria-label="成熟度"]').setValue('SINGLE_PROJECT_PRODUCTION')
    expect(wrapper.emitted('update:maturity')).toEqual([['SINGLE_PROJECT_PRODUCTION']])
  })

  it('keeps claimed and verified outcomes separate and traceable on the shared detail page', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/items/[id].vue'), 'utf8')

    expect(page).toContain('发布方声称的成效')
    expect(page).toContain('独立证据支持的成效')
    expect(page).toContain('openOutcomeEvidence')
    expect(page).toContain('复制条件')
    expect(page).toContain('限制与风险')
    expect(page).toContain('技术调研')
    expect(page).not.toContain('建议采购')
  })

  it('lets reviewers amend classifications, maturity, and outcome attribution', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/review/[id].vue'), 'utf8')

    expect(page).toContain('digital_case_patch')
    expect(page).toContain('工程专业代码')
    expect(page).toContain('应用场景代码')
    expect(page).toContain('成熟度')
    expect(page).toContain('成效归因')
  })
})
