import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const eventId = '019f7c00-0000-7000-8000-000000000011'
const claimId = '019f7c00-0000-7000-8000-000000000012'

const fullProjection = {
  projection_kind: 'FULL',
  event_id: eventId,
  title: '隧道瓦斯监测系统投入运营',
  primary_type: 'SAFETY_INTELLIGENCE',
  facets: { engineering_objects: ['TUNNEL'], specialties: ['TUNNEL_GAS_MONITORING'], equipment: [] },
  source: { name: '国家矿山安全监察局', official: true },
  source_published_at: '2026-07-18T01:00:00Z',
  first_discovered_at: '2026-07-18T01:05:00Z',
  source_excerpt: { text: '项目在运营隧道部署瓦斯监测与联动预警。', claim_ids: [claimId], evidence_locators: ['p:3'] },
  ai_summary: {
    status: 'SUCCEEDED', body: '发生了什么：项目部署监测系统。\n工程影响与意义：支持现场预警。\n限制与待跟踪：长期效果仍需跟踪。',
    claim_ids: [claimId], judgment_paragraphs: [2, 3], model: 'deepseek-chat', generated_at: '2026-07-18T02:00:00Z',
  },
  original_url: 'https://example.com/tunnel-gas',
  claim_basis: ['AUTHORITY_FINDING'], hotspot: null, media: [], attachments: [], correction_alert: null,
}

async function mockAncillary(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/api/v1/version', route => route.fulfill({ json: { api_version: 'v2', content_schema_version: '2.0.0' } }))
  await page.route('**/api/v1/sources', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/source-discovery/settings', route => route.fulfill({ json: { automation_enabled: false } }))
}

test('v2 home starts empty and places search above 今日精选', async ({ page }) => {
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({
    json: { items: [], next_cursor: null, generated_at: '2026-07-19T01:00:00Z', projection_generation: 'v2' },
  }))
  await page.goto('/')
  const search = page.getByRole('search')
  const heading = page.getByRole('heading', { level: 1, name: '今日精选' })
  await expect(search).toBeVisible()
  await expect(heading).toBeVisible()
  expect(await search.evaluate((node, target) => Boolean(node.compareDocumentPosition(target as Node) & Node.DOCUMENT_POSITION_FOLLOWING), await heading.elementHandle())).toBe(true)
  await expect(page.getByText('暂无精选内容')).toBeVisible()
})

test('v2 full reader keeps evidence first and diagnostics folded', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))
  await page.route(`**/api/v2/events/${eventId}/appendix`, route => route.fulfill({
    json: { event_id: eventId, claims: [], evidence: [], automatic_results: [], relationships: [], corrections: [] },
  }))
  await page.goto(`/events/${eventId}`)
  await expect(page.getByRole('heading', { level: 1, name: fullProjection.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toBeVisible()
  const appendix = page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })
  await expect(appendix).toHaveAttribute('aria-expanded', 'false')
  await appendix.click()
  await expect(page.getByText('Accepted claims：0')).toBeVisible()
})

test('v2 R3 reader exposes metadata only and unprojected R4 is not found', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: {
    projection_kind: 'R3_METADATA', event_id: eventId, title: '待审核安全初报', primary_type: 'SAFETY_INTELLIGENCE',
    source_name: '权威机关', official_source: true, source_published_at: null,
    first_discovered_at: '2026-07-19T01:00:00Z', original_url: 'https://example.com/r3', review_state: 'PENDING_OWNER_REVIEW',
  } }))
  await page.goto(`/events/${eventId}`)
  await expect(page.getByText('待 Owner 审核')).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toHaveCount(0)

  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ status: 404, json: { detail: 'Event not found' } }))
  await page.reload()
  await expect(page.getByText(/不可见|无法响应|not found/i)).toBeVisible()
})

test('v2 empty home has no serious accessibility violations @a11y', async ({ page }) => {
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({
    json: { items: [], next_cursor: null, generated_at: '2026-07-19T01:00:00Z', projection_generation: 'v2' },
  }))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
})
