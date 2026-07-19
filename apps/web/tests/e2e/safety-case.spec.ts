import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mockV2Event, v2Feed, v2Projection } from './v2-fixtures'

const event = {
  id: '019b0000-0000-7000-8000-000000004001',
  title: '高速公路边坡事故正式调查报告',
  source_name: '事故调查组',
  source_published_at: '2026-07-10T01:00:00Z',
  first_discovered_at: '2026-07-10T01:05:00Z',
  original_url: 'https://example.com/investigation',
  domain: 'SAFETY',
  content_type: 'SAFETY_CASE',
  one_sentence_fact: '有权机关发布了事故调查报告。',
}

async function mockSafetyFeed(page: Page): Promise<void> {
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([event]) }))
}

test('/all and /safety use the same v2 Event projection without v1 content fallback', async ({ page }) => {
  await mockSafetyFeed(page)
  for (const path of ['/all', '/safety']) {
    await page.goto(path)
    await expect(page.getByText(event.title)).toBeVisible()
    await expect(page.getByText(event.source_name)).toBeVisible()
  }
  await expect(page.getByText('安全案例', { exact: true })).toBeVisible()
})

test('FULL safety Event reader keeps source fact and AI judgment semantically separate', async ({ page }) => {
  await mockV2Event(page, event)
  await page.goto(`/events/${event.id}`)

  await expect(page.getByRole('heading', { level: 1, name: event.title })).toBeVisible()
  await expect(page.getByText(event.one_sentence_fact)).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toBeVisible()
  await expect(page.getByText('AI 总结暂不可用', { exact: false })).toBeVisible()
  await expect(page.getByText('官方已核验')).toHaveCount(0)
})

test('R3 safety Event exposes metadata but no excerpt, AI, media, or appendix', async ({ page }) => {
  await page.route(`**/api/v2/events/${event.id}`, route => route.fulfill({
    json: v2Projection(event, { risk: 'R3_METADATA', official: true }),
  }))
  await page.goto(`/events/${event.id}`)

  await expect(page.getByText('待 Owner 审核')).toBeVisible()
  await expect(page.getByText(event.source_name)).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })).toHaveCount(0)
})

test('@a11y safety Event feed and mobile reader have no axe violations', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await mockSafetyFeed(page)
  await mockV2Event(page, event)
  await page.goto('/safety')
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.goto(`/events/${event.id}`)
  await expect(page.getByRole('heading', { name: event.title })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768)
})
