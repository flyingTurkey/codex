import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mockV2Event, v2Feed } from './v2-fixtures'

const digital = {
  id: '019b0000-0000-7000-8000-000000005201',
  title: '智慧梁厂 2.0',
  source_name: '蜀道集团',
  source_published_at: '2022-03-10T00:00:00Z',
  first_discovered_at: '2026-07-14T04:05:00Z',
  original_url: 'https://www.shudaojt.com/public/example.pdf',
  domain: 'DIGITAL',
  content_type: 'DIGITAL_CASE',
  one_sentence_fact: '企业公开材料描述了智慧梁厂应用。',
}

async function mockDigital(page: Page): Promise<void> {
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([digital]) }))
  await mockV2Event(page, digital, { official: false })
  await page.route(`**/api/v1/items/${digital.id}`, route => route.fulfill({ status: 404 }))
}

test('digital feed uses v2 cards and never revives legacy multidimensional scores', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await mockDigital(page)
  await page.goto('/digital')

  await expect(page.getByRole('heading', { level: 1, name: '数字化案例' })).toBeVisible()
  await expect(page.getByText(digital.title)).toBeVisible()
  await expect(page.getByText(digital.source_name)).toBeVisible()
  await expect(page.getByTestId('score-summary')).toHaveCount(0)
  await expect(page.getByText('可信度')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('digital FULL reader keeps accepted source excerpt and appendix on v2', async ({ page }) => {
  await mockDigital(page)
  await page.goto(`/events/${digital.id}`)

  await expect(page.getByRole('heading', { level: 1, name: digital.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByText(digital.one_sentence_fact)).toBeVisible()
  await expect(page.getByText('官方已核验')).toHaveCount(0)
  const appendix = page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })
  await appendix.click()
  await expect(appendix).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByText('附录当前没有治理记录。')).toBeVisible()
})

test('legacy classification approval route remains retired', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('button', { name: '批准并发布' })).toHaveCount(0)
})

test('@a11y digital feed and FULL reader have no axe violations', async ({ page }) => {
  await mockDigital(page)
  await page.goto('/digital')
  await expect(page.getByText(digital.title)).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.goto(`/events/${digital.id}`)
  await expect(page.getByRole('heading', { name: digital.title })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
