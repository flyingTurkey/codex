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
  await page.route('**/api/v1/admin/source-candidates**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ has_more: false, items: [], next_cursor: null, status_counts: {} }),
  }))
  await page.route('**/api/v1/admin/source-streams**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ has_more: false, items: [], next_cursor: null }),
  }))
  await page.route('**/api/v1/admin/source-attention**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ has_more: false, items: [], next_cursor: null }),
  }))
}

async function openSourceCenter(page: Page): Promise<void> {
  await page.goto('/')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  await page.getByRole('link', { name: '管理入口', exact: true }).click()
}

test('source admin opens a blank, default-denied candidate discovery form', async ({ page }) => {
  await mockEmptySourceCenter(page)
  await openSourceCenter(page)
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  await expect(page.getByRole('heading', { level: 1, name: '来源中心' })).toBeVisible()
  await expect(page.getByText('服务端资格包', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '提交发现 URL', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '提交发现 URL' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByLabel('公开 URL')).toHaveValue('')
  await expect(drawer.getByLabel('提交原因')).toHaveValue('')
  await expect(drawer.getByText(/不能声明已批准或已启用/)).toBeVisible()
  await expect(drawer.getByLabel(/状态|ACTIVE|批准单号/)).toHaveCount(0)
  await expect(drawer.getByRole('button', { name: /启用/ })).toHaveCount(0)
})

test('@a11y source registry list has no axe violations', async ({ page }) => {
  await mockEmptySourceCenter(page)
  await openSourceCenter(page)
  await expect(page.getByRole('heading', { level: 1, name: '来源中心' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
