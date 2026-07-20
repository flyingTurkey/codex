import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { v2Feed } from './v2-fixtures'

const event = {
  id: '019b1000-0000-7000-8000-000000000001',
  title: '四川公路隧道监测预警工作指引',
  source_name: '四川省交通运输厅',
  source_published_at: '2026-07-15T00:30:00Z',
  first_discovered_at: '2026-07-15T01:00:00Z',
  original_url: 'https://jtyst.sc.gov.cn/example',
  domain: 'SAFETY',
  content_type: 'SAFETY_REGULATION',
}

async function mockPortal(page: Page): Promise<void> {
  await page.route('**/api/v2/search**', route => route.fulfill({ json: v2Feed([event]) }))
  await page.route('**/api/v1/saved-events', route => route.fulfill({ status: 204 }))
  await page.route(`**/api/v1/items/${event.id}`, route => route.fulfill({ status: 404 }))
  await page.route('**/api/v1/daily', route => route.fulfill({
    json: {
      id: '019b1000-0000-7000-8000-000000000003',
      published_at: '2026-07-15T01:10:00Z',
      report_date: '2026-07-15',
      requires_regeneration: false,
      sections: [{
        items: [{
          current_state: 'PUBLISHED',
          item_id: event.id,
          original_url: event.original_url,
          position: 1,
          publication_revision_id: '019b1000-0000-7000-8000-000000000002',
          summary: '围绕公路隧道监测预警建立分级处置要求。',
          title: event.title,
        }],
        kind: 'TODAY_HIGHLIGHTS',
        title: '今日重点',
      }],
      snapshot_at: '2026-07-15T01:00:00Z',
      status: 'PUBLISHED',
    },
  }))
}

test('v2 exact search can save an Event and reach the retained v1 daily report', async ({ page }) => {
  await mockPortal(page)
  await page.goto('/search?q=%E5%B7%9D%E4%BA%A4%E8%A7%84')

  await expect(page.getByRole('heading', { level: 1, name: '搜索' })).toBeVisible()
  await expect(page.getByRole('link', { name: event.title, exact: true })).toBeVisible()
  await expect(page.getByText(event.source_name)).toBeVisible()
  const save = page.getByRole('button', { name: '收藏', exact: true })
  await save.click()
  await expect(page.getByRole('button', { name: '已收藏', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )

  await page.getByRole('link', { name: '行业日报', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '行业日报' })).toBeVisible()
  await expect(page.getByText('已审核发布', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: '今日重点' })).toBeVisible()
  await expect(page.getByText('围绕公路隧道监测预警建立分级处置要求。')).toBeVisible()
  await expect(page.getByRole('button', { name: '生成今日草稿' })).toHaveCount(0)
})

test('@a11y v2 search and retained v1 daily are readable at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await mockPortal(page)
  for (const path of ['/search?q=tunnel', '/daily']) {
    await page.goto(path)
    await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false')
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768)
  }
})
