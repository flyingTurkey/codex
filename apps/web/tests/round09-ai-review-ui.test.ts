import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const item = {
  activity_at: '2026-07-15T03:00:00Z',
  ai_assistance: {
    accepted_claims_only: true,
    generated_at: '2026-07-15T03:00:00Z',
    model_profile: 'mock-v1',
    pipeline_run_id: '019b0000-0000-7000-8000-000000009003',
    prompt_version: 'summary-v1',
    schema_version: 'summary-schema-v1',
    status: 'ASSISTED',
  },
  content_type: 'DIGITAL_CASE',
  domain: 'DIGITAL',
  first_discovered_at: '2026-07-15T03:00:00Z',
  id: '019b0000-0000-7000-8000-000000009001',
  one_sentence_fact: '仅由已接受事实生成的审核后摘要。',
  original_url: 'https://example.com/case',
  publication_revision_id: '019b0000-0000-7000-8000-000000009002',
  review_status: 'APPROVED',
  revision_state: {
    action: 'REVISE',
    created_at: '2026-07-15T03:00:00Z',
    revision_number: 2,
    withdrawn_at: null,
  },
  source_name: '官方来源',
  source_published_at: '2026-07-15T03:00:00Z',
  title: 'AI 辅助审核案例',
} as unknown as ItemSummary

describe('round 09 governed AI review UI', () => {
  it('shows AI assistance, revision state and accepted-claim summary', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item } })
    expect(wrapper.text()).toContain('AI 辅助 · 已受控校验')
    expect(wrapper.text()).toContain('第 2 版修订')
    expect(wrapper.text()).toContain('仅由已接受事实生成的审核后摘要。')
  })

  it('does not render an AI summary when accepted-claim binding is absent', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const unsafeItem = structuredClone(item)
    if (unsafeItem.ai_assistance) unsafeItem.ai_assistance.accepted_claims_only = false
    const wrapper = mount(IntelligenceCard, { props: { item: unsafeItem } })
    expect(wrapper.text()).not.toContain('仅由已接受事实生成的审核后摘要。')
  })

  it('retires the enterprise workbench while preserving evidence on personal details', () => {
    expect(existsSync(resolve(process.cwd(), 'app/components/ReviewWorkbench.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/review/[id].vue'))).toBe(false)
    const detail = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')
    expect(detail).toContain('Accepted claims')
    expect(detail).toContain('/appendix')
  })
})
