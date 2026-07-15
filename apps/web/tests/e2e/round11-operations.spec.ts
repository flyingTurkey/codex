import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const overview = {
  observed_at: '2026-07-15T06:00:00Z',
  metrics: [
    { code: 'UNHEALTHY_SOURCES', value: 0, unit: 'count', status: 'PASS' },
    { code: 'OPEN_SOURCE_CIRCUITS', value: 0, unit: 'count', status: 'PASS' },
    { code: 'PENDING_REVIEWS', value: 4, unit: 'count', status: 'UNKNOWN' },
    { code: 'PUBLISHER_OUTBOX_DEPTH', value: 1, unit: 'count', status: 'UNKNOWN' },
    { code: 'FAILED_TASKS', value: 0, unit: 'count', status: 'PASS' },
    { code: 'QUEUED_REPLAYS', value: 0, unit: 'count', status: 'UNKNOWN' },
  ],
}

async function mockOperations(page: Page): Promise<void> {
  await page.route('**/api/v1/admin/operations/overview', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(overview),
  }))
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: '运行管理员',
      roles: ['platform_admin'],
      user_id: '019b0000-0000-7000-8000-000000000011',
    }),
  }))
}

test('operations center reuses the application shell and stable visual system', async ({ page }) => {
  await mockOperations(page)
  await page.goto('/admin/operations')
  await expect(page.getByRole('heading', { level: 1, name: '运行中心' })).toBeVisible()
  await expect(page.getByText('失败任务', { exact: true })).toBeVisible()
  await expect(page.locator('.srbg-app-shell')).toHaveScreenshot('round11-operations.png')
})

test('@a11y operations views support keyboard, 200% equivalent viewport, and axe', async ({
  page,
}) => {
  await page.setViewportSize({ width: 720, height: 450 })
  await mockOperations(page)
  for (const path of ['/admin/source-health', '/admin/operations', '/admin/quality']) {
    await page.goto(path)
    await page.keyboard.press('Tab')
    await page.keyboard.press('Enter')
    await expect(page.getByRole('main')).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(720)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  }
})
