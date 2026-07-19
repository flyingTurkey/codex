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
  await page.route('**/api/v2/hotspots**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(v2Feed([hotspot])),
  }))
}

test('v2 hotspots keep heat separate from confidence and expose evidence-backed cards', async ({ page }) => {
  await mockHotspots(page)
  await page.goto('/hot')

  await expect(page.getByRole('heading', { level: 3, name: hotspot.title })).toBeVisible()
  await expect(page.getByText(hotspot.source_name)).toBeVisible()
  await expect(page.getByText('安全案例', { exact: true })).toBeVisible()
  await expect(page.getByText(/置信度\s*\d/)).toHaveCount(0)
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
