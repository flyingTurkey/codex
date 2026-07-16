import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockEmptySourceCenter(page: Page): Promise<void> {
  await page.route('**/api/v1/feed**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      fingerprint: 'sha256:source-registry-empty',
      freshness: 'fresh',
      generated_at: '2026-07-16T06:00:00Z',
      items: [],
      next_cursor: null,
      notices: [],
    }),
  }))
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: '来源管理员',
      local_identity: true,
      roles: ['source_admin'],
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
  await page.route('**/api/v1/admin/sources', route => route.fulfill({
    contentType: 'application/json',
    body: '[]',
  }))
}

async function openSourceCenter(page: Page): Promise<void> {
  await page.goto('/')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  await page.getByRole('link', { name: '管理入口', exact: true }).click()
}

test('source admin opens a blank, default-denied candidate registration', async ({ page }) => {
  await mockEmptySourceCenter(page)
  await openSourceCenter(page)
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  await expect(page.getByRole('heading', { level: 1, name: '来源中心 V2' })).toBeVisible()
  await expect(page.getByText('默认拒绝', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '登记候选来源', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '登记候选来源' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByLabel('来源名称')).toHaveValue('')
  await expect(drawer.getByLabel('公开基础 URL')).toHaveValue('')
  await expect(drawer.getByLabel('治理责任人 ID')).toHaveValue('')
  await expect(drawer.getByText(/不批准、不试运行，也不发起任何网络请求/)).toBeVisible()
  await expect(drawer.getByLabel(/状态|ACTIVE|批准单号/)).toHaveCount(0)
  await expect(drawer.locator('textarea')).toHaveCount(0)
})

test('@a11y source registry list has no axe violations', async ({ page }) => {
  await mockEmptySourceCenter(page)
  await openSourceCenter(page)
  await expect(page.getByRole('heading', { level: 1, name: '来源中心 V2' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
