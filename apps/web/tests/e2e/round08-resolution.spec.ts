import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockHotTopics(page: Page): Promise<void> {
  await page.route('**/api/v1/hot-topics**', route => route.fulfill({
    json: {
      auto_merge_enabled: false,
      evaluation_status: 'INTERNAL_TEST_FIXTURE',
      generated_at: '2026-07-15T03:00:00Z',
      items: [{
        domain: 'SAFETY',
        event_count: 3,
        heat_score: 76,
        id: '019b0000-0000-7000-8000-000000008104',
        independent_source_count: 2,
        latest_activity_at: '2026-07-15T02:00:00Z',
        title: '汛期道路边坡安全动态',
      }],
      window: '7d',
    },
  }))
}

test('hot topics explain independent sources and keep heat separate from confidence', async ({ page }) => {
  await mockHotTopics(page)
  await page.goto('/hot')
  await expect(page.getByRole('heading', { level: 2, name: '汛期道路边坡安全动态' })).toBeVisible()
  await expect(page.getByText('独立信源').last()).toBeVisible()
  await expect(page.getByText('内测评估 / 自动合并关闭')).toBeVisible()
  await expect(page.getByText(/置信度\s*\d/)).toHaveCount(0)
})

test('relationship approval workbench retires to automatic owner relationships', async ({ page }) => {
  await page.goto('/admin/clusters')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('button', { name: '确认关系' })).toHaveCount(0)
})

test('@a11y hot topics and retired relation route have no axe violations', async ({ page }) => {
  await mockHotTopics(page)
  await page.goto('/hot')
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.goto('/admin/clusters')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
