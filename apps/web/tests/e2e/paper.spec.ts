import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const itemId = '019b0000-0000-7000-8000-000000006201'
const item = {
  activity_at: '2026-07-15T04:00:00Z',
  content_type: 'JOURNAL_PAPER',
  domain: 'DIGITAL',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-15T04:05:00Z',
  id: itemId,
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
    engineering_domains: ['BRIDGE'],
    journal: '中国公路学报',
    kind: 'JOURNAL_PAPER',
    maturity_level: 'LAB_PROTOTYPE',
    open_status: 'CLOSED',
    paper_type: 'ARTICLE',
    relation_status: 'CORRECTED',
    technology_tags: ['DIGITAL_TWIN'],
    year: 2025,
    doi: '10.1000/bridge.2025.1',
  },
}
const paper = {
  abstract: null,
  abstract_availability: 'LICENCE_UNCLEAR',
  access_level: 'METADATA_ONLY',
  authors: [{ name: '张三', orcid: null, institutions: ['西南交通大学'] }],
  doi: '10.1000/bridge.2025.1',
  engineering_domains: ['BRIDGE'],
  issns: ['1001-7372'],
  issue: '7',
  journal: '中国公路学报',
  keywords: ['桥梁', '数字孪生'],
  maturity_level: 'LAB_PROTOTYPE',
  open_fulltext_url: null,
  open_status: 'CLOSED',
  pages: '1-12',
  relation_status: 'CORRECTED',
  research_interpretation: null,
  similar_papers: [],
  technology_tags: ['DIGITAL_TWIN'],
  volume: '38',
  year: 2025,
}

async function mockPaper(page: Page): Promise<void> {
  await page.route('**/api/v1/feed**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      fingerprint: 'sha256:round06-e2e', freshness: 'fresh',
      generated_at: '2026-07-15T04:10:00Z', items: [item], next_cursor: null, notices: [],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ item, claims: [], evidence: [], paper }),
  }))
  await page.route(`**/api/v1/items/${itemId}/citation**`, (route) => route.fulfill({
    contentType: 'text/plain; charset=utf-8',
    body: '张三. 桥梁数字孪生研究[J]. 中国公路学报, 2025.',
  }))
  await page.route(`**/api/v1/events/${itemId}`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      id: itemId, title: item.title, event_type: 'RESEARCH_RESULT', event_status: 'ACTIVE',
      canonical_event_id: itemId, event_version: 1, confirmed_facts: [], unverified_facts: [],
      timeline: { items: [] }, relations: [], similar_scenario_tags: [],
      prevention_measure_tags: [], topic_ids: [], independent_source_count: 1,
    }),
  }))
  await page.route(`**/api/v1/events/${itemId}/content`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ item, claims: [], evidence: [], paper }),
  }))
  await page.route(`**/api/v1/events/${itemId}/citation**`, (route) => route.fulfill({
    contentType: 'text/plain; charset=utf-8',
    body: '寮犱笁. 妗ユ鏁板瓧瀛敓鐮旂┒[J]. 涓浗鍏矾瀛︽姤, 2025.',
  }))
}

test('paper tab filters and shared card expose access and research boundaries', async ({ page }) => {
  await mockPaper(page)
  await page.goto('/digital')
  await page.getByRole('button', { name: '期刊论文' }).click()

  await expect(page.getByRole('heading', { level: 1, name: '期刊论文' })).toBeVisible()
  await expect(page.getByText('10.1000/bridge.2025.1')).toBeVisible()
  await expect(page.getByTestId('paper-summary').getByText('仅题录')).toBeVisible()
  await expect(page.getByText('研究结果不代表已完成工程生产应用。')).toBeVisible()
  await page.getByLabel('论文类型').selectOption('ARTICLE')
  await page.getByLabel('开放状态').selectOption('METADATA_ONLY')
})

test('@a11y paper detail separates metadata, abstract and fulltext without axe violations', async ({ page }) => {
  await mockPaper(page)
  await page.goto(`/events/${itemId}`)

  await expect(page.getByRole('heading', { level: 1, name: item.title })).toBeVisible()
  await expect(page.getByText('许可不明确，未收录摘要。')).toBeVisible()
  await expect(page.getByText('平台未保存全文，仅提供题录与原文链接。')).toBeVisible()
  await expect(page.getByRole('link', { name: '导出 RIS' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
