import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mockV2Event, v2Feed } from './v2-fixtures'

const product = {
  id: '019b0000-0000-7000-8000-000000007201',
  title: '经纬 M350 RTK 无人机平台',
  source_name: '厂商一手来源',
  source_published_at: '2026-05-01T00:00:00Z',
  first_discovered_at: '2026-07-15T04:05:00Z',
  original_url: 'https://enterprise.dji.com/cn/example',
  domain: 'DIGITAL',
  content_type: 'LOW_ALTITUDE_EQUIPMENT',
  one_sentence_fact: '厂商公开了设备型号与用途，尚无独立效果验证。',
}

async function mockProduct(page: Page): Promise<void> {
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([product]) }))
  await mockV2Event(page, product, { official: false })
  await page.route(`**/api/v1/items/${product.id}`, route => route.fulfill({ status: 404 }))
}

test('product category reuses v2 feed and does not manufacture legacy product scores', async ({ page }) => {
  await mockProduct(page)
  await page.goto('/digital')
  await expect(page.locator('.srbg-app-shell[aria-busy]')).toHaveAttribute('aria-busy', 'false', { timeout: 20_000 })
  await page.getByRole('button', { name: '低空设备' }).click()

  await expect(page.getByRole('heading', { level: 1, name: '技术产品' })).toBeVisible()
  await expect(page.getByRole('button', { name: '低空设备' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText(product.title)).toBeVisible()
  await expect(page.getByText(product.source_name)).toBeVisible()
  await expect(page.getByTestId('score-summary')).toHaveCount(0)
  await expect(page.getByText('官方已核验')).toHaveCount(0)
})

test('@a11y product reader keeps manufacturer attribution and evidence boundary', async ({ page }) => {
  await mockProduct(page)
  await page.goto(`/events/${product.id}`)

  await expect(page.getByRole('heading', { level: 1, name: product.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByText(product.one_sentence_fact)).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toBeVisible()
  await expect(page.getByRole('link', { name: '查看原文' })).toHaveAttribute(
    'href',
    product.original_url,
  )
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
