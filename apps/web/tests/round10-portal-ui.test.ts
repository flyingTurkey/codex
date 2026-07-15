import { mount } from '@vue/test-utils'
import type { DailyReport, ItemSummary } from '@srbg/contracts'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const item = {
  activity_at: '2026-07-15T03:00:00Z',
  content_type: 'SAFETY_REGULATION',
  domain: 'SAFETY',
  first_discovered_at: '2026-07-15T03:00:00Z',
  id: '019b0000-0000-7000-8000-000000009001',
  is_saved: false,
  original_url: 'https://example.com/regulation',
  publication_revision_id: '019b0000-0000-7000-8000-000000009002',
  review_status: 'APPROVED',
  search_context: {
    match_kind: 'EXACT_IDENTIFIER',
    matched_fields: ['DOCUMENT_NUMBER'],
    matched_identifiers: ['川交规〔2026〕10号'],
    semantic_status: 'DISABLED',
  },
  source_name: '四川省交通运输厅',
  source_published_at: '2026-07-15T03:00:00Z',
  title: '隧道监测预警规定',
} as unknown as ItemSummary

describe('round 10 search daily and saved UI', () => {
  it('submits a trimmed global search query', async () => {
    const GlobalSearch = componentModules['../app/components/GlobalSearch.vue']?.default
    expect(GlobalSearch).toBeDefined()
    if (!GlobalSearch) return
    const wrapper = mount(GlobalSearch)
    await wrapper.get('input').setValue('  隧道+监测预警+四川  ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('search')).toEqual([['隧道+监测预警+四川']])
  })

  it('extends the existing card with exact-match evidence and an accessible save action', async () => {
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue(undefined))
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return
    const wrapper = mount(IntelligenceCard, { props: { item } })
    expect(wrapper.text()).toContain('精确编号命中')
    expect(wrapper.text()).toContain('川交规〔2026〕10号')
    const save = wrapper.get('[data-testid="save-item"]')
    expect(save.attributes('aria-pressed')).toBe('false')
    await save.trigger('click')
    expect(save.attributes('aria-pressed')).toBe('true')
    vi.unstubAllGlobals()
  })

  it('renders withdrawn daily snapshot entries with text, not color alone', () => {
    const DailyReportView = componentModules['../app/components/DailyReportView.vue']?.default
    expect(DailyReportView).toBeDefined()
    if (!DailyReportView) return
    const report = {
      id: '019b0000-0000-7000-8000-000000009010',
      published_at: '2026-07-15T03:00:00Z',
      report_date: '2026-07-15',
      requires_regeneration: false,
      sections: [{
        items: [{
          current_state: 'WITHDRAWN',
          item_id: item.id,
          original_url: item.original_url,
          position: 1,
          publication_revision_id: item.publication_revision_id,
          summary: null,
          title: item.title,
        }],
        kind: 'TODAY_HIGHLIGHTS',
        title: '今日重点',
      }],
      snapshot_at: '2026-07-15T02:00:00Z',
      status: 'PUBLISHED',
    } as DailyReport
    const wrapper = mount(DailyReportView, { props: { report } })
    expect(wrapper.text()).toContain('已撤回')
    expect(wrapper.text()).not.toContain('旧摘要')
  })

  it('keeps search and saved results on the shared feed/card path', () => {
    const searchPage = readFileSync(resolve(process.cwd(), 'app/pages/search.vue'), 'utf8')
    const savedPage = readFileSync(resolve(process.cwd(), 'app/pages/saved.vue'), 'utf8')
    expect(searchPage).toContain('IntelligenceFeedPage')
    expect(savedPage).toContain('IntelligenceFeedPage')
    expect(searchPage).not.toContain('new IntelligenceCard')
    expect(savedPage).not.toContain('new IntelligenceCard')
  })

  it('appends cursor pages through the shared feed load-more contract', () => {
    const searchPage = readFileSync(resolve(process.cwd(), 'app/pages/search.vue'), 'utf8')
    const savedPage = readFileSync(resolve(process.cwd(), 'app/pages/saved.vue'), 'utf8')
    for (const page of [searchPage, savedPage]) {
      expect(page).toContain('@load-more="loadMore"')
      expect(page).toContain('current.next_cursor')
      expect(page).toContain('items: [...current.items, ...next.items]')
    }
  })
})
