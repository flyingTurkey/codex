import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { v2Feed } from './v2-fixtures'

const hotspot = {
  id: '019b0000-0000-7000-8000-000000008104',
  title: '汛期道路边坡安全动态',
  source_name: '权威来源',
  source_published_at: '2026-07-15T02:00:00Z',
  first_discovered_at: '2026-07-15T02:05:00Z',
  original_url: 'https://example.com/hotspot',
  domain: 'SAFETY',
  content_type: 'SAFETY_CASE',
}

async function mockHotspots(page: Page): Promise<void> {
  const pagePayload = v2Feed([hotspot])
  pagePayload.items[0] = {
    ...pagePayload.items[0],
    projection_kind: 'FULL',
    primary_type: 'SAFETY_INTELLIGENCE',
    facets: { engineering_objects: ['TUNNEL'], specialties: [], equipment_domains: [], cross_type_tags: [] },
    source: { name: hotspot.source_name, official: true },
    human_reviewed: false,
    source_excerpt: {
      text: '权威材料记录了汛期道路边坡安全处置事实。',
      claim_ids: ['019b0000-0000-7000-8000-000000008105'],
      evidence_locators: ['html:p:1'],
    },
    ai_summary: {
      status: 'NOT_GENERATED',
      status_message: 'AI 总结尚未生成。已通过证据门禁的原文摘录仍可阅读。',
      paragraphs: [],
      claim_ids: [],
      judgment_paragraphs: [],
    },
    claim_basis: ['AUTHORITY_FINDING'],
    hotspot: {
      trigger: 'MULTI_SOURCE_7D',
      independent_source_count: 2,
      reasons: ['两份独立来源均有 AcceptedClaim 支持'],
    },
    media: [], attachments: [], correction_alert: null,
  }
  await page.route('**/api/v2/hotspots**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(pagePayload),
  }))
}

test('v2 hotspots keep heat separate from confidence and expose evidence-backed cards', async ({ page }) => {
  await mockHotspots(page)
  await page.goto('/hot')

  await expect(page.getByRole('heading', { level: 3, name: hotspot.title })).toBeVisible()
  await expect(page.getByText(hotspot.source_name)).toBeVisible()
  await expect(page.getByText('安全案例', { exact: true })).toBeVisible()
  await expect(page.getByText(/7 天内多源触发/)).toBeVisible()
  await expect(page.getByText(/2 个独立来源/)).toBeVisible()
  await expect(page.getByText(/两份独立来源均有 AcceptedClaim 支持/)).toBeVisible()
  await expect(page.getByText(/置信度\s*\d/)).toHaveCount(0)
  await expect(page.getByText(/总分\s*\d/)).toHaveCount(0)
})

test('relationship approval workbench retires while v1 correction seam remains separate', async ({ page }) => {
  await page.goto('/admin/clusters')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('button', { name: '确认关系' })).toHaveCount(0)
})

test('@a11y v2 hotspots and retired relation route have no axe violations', async ({ page }) => {
  await mockHotspots(page)
  await page.goto('/hot')
  await expect(page.getByRole('heading', { name: '热点榜单' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.goto('/admin/clusters')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
