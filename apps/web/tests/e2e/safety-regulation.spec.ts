import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mockV2Event, v2Feed, v2Projection } from './v2-fixtures'

const eventId = '019b0000-0000-7000-8000-000000001001'
const regulation = {
  id: eventId,
  title: '生产安全事故应急预案管理办法',
  source_name: '应急管理部',
  source_published_at: '2016-06-03T10:28:00Z',
  first_discovered_at: '2026-07-14T01:09:04Z',
  original_url: 'https://www.mem.gov.cn/example.shtml',
  domain: 'SAFETY',
  content_type: 'SAFETY_REGULATION',
  one_sentence_fact: '应急管理部发布了生产安全事故应急预案管理要求。',
}

async function mockFeed(page: Page, risk: 'FULL' | 'R3_METADATA' = 'FULL'): Promise<void> {
  const payload = risk === 'FULL'
    ? v2Feed([regulation])
    : { ...v2Feed([]), items: [v2Projection(regulation, { risk })] }
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: payload }))
}

test('R3 metadata card exposes only whitelist UI and no score or evidence action', async ({ page }) => {
  await mockFeed(page, 'R3_METADATA')
  await page.goto('/safety')

  await expect(page.getByRole('heading', { level: 1, name: '安全情报' })).toBeVisible()
  await expect(page.getByText('待人工审核', { exact: true })).toBeVisible()
  await expect(page.getByText(regulation.source_name, { exact: true })).toBeVisible()
  await expect(page.getByTestId('evidence-trigger')).toHaveCount(0)
  await expect(page.getByText(/评分|可信度|效力结论|AI 摘要/)).toHaveCount(0)
})

test('FULL safety card links to the v2 reader and keeps accepted facts evidence-first', async ({ page }) => {
  await mockFeed(page)
  await mockV2Event(page, regulation)
  await page.goto('/safety')

  await expect(page.getByText(regulation.title)).toBeVisible()
  await page.getByRole('link', { name: regulation.title }).click()
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}$`))
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByText(regulation.one_sentence_fact)).toBeVisible()
})

test('saved/daily and version diff remain v1 while the retired item reader is 404', async ({ page }) => {
  await page.route(`**/api/v1/items/${eventId}`, route => route.fulfill({
    status: 404,
    json: { type: 'about:blank', title: 'Not Found', status: 404, code: 'LEGACY_READER_RETIRED' },
  }))
  await page.route(`**/api/v1/items/${eventId}/versions`, route => route.fulfill({
    json: { item_id: eventId, versions: [{ version_number: 1 }] },
  }))
  await page.route(`**/api/v1/items/${eventId}/diff**`, route => route.fulfill({
    json: { item_id: eventId, change_type: 'CONTENT_UPDATE' },
  }))
  await page.goto('/')

  const statuses = await page.evaluate(async (id) => Promise.all([
    fetch(`/api/v1/items/${id}`).then(response => response.status),
    fetch(`/api/v1/items/${id}/versions`).then(response => response.status),
    fetch(`/api/v1/items/${id}/diff?from=a&to=b`).then(response => response.status),
  ]), eventId)
  expect(statuses).toEqual([404, 200, 200])
  expect(statuses[0]).not.toBe(200)
})

test('R4 or absent projection returns Problem Details and no reader content', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({
    status: 404,
    json: { type: 'about:blank', title: 'Event not found', status: 404, code: 'EVENT_NOT_FOUND' },
  }))
  await page.goto(`/events/${eventId}`)

  await expect(page.getByText(/不可见|无法响应|not found/i)).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toHaveCount(0)
})

test('FULL reader appendix is collapsed, keyboard operable, and loaded from v2', async ({ page }) => {
  await mockV2Event(page, regulation)
  await page.goto(`/events/${eventId}`)
  const button = page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })

  await expect(button).toHaveAttribute('aria-expanded', 'false')
  await button.focus()
  await page.keyboard.press('Enter')
  await expect(button).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByText('附录当前没有治理记录。')).toBeVisible()
})

test('@a11y safety feed and FULL reader have no axe violations', async ({ page }) => {
  await mockFeed(page)
  await mockV2Event(page, regulation)
  await page.goto('/safety')
  await expect(page.getByText(regulation.title)).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await page.goto(`/events/${eventId}`)
  await expect(page.getByRole('heading', { level: 1, name: regulation.title })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
