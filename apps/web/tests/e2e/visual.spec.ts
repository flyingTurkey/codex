import { expect, test, type Page } from '@playwright/test'

const visualViewports = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1024x768', width: 1024, height: 768 },
  { name: '768x1024', width: 768, height: 1024 },
] as const

async function normalizeDynamicPageData(page: Page): Promise<void> {
  const updatedAt = page.getByTestId('page-updated-at')
  await expect(updatedAt).toBeVisible()
  await updatedAt.evaluate((element) => {
    element.setAttribute('datetime', '2026-07-13T14:30:00.000Z')
    element.textContent = '2026-07-13 22:30'
  })
}

async function mockVisualIdentity(page: Page): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: '视觉基线用户',
      local_identity: true,
      roles: ['viewer', 'source_admin', 'reviewer'],
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
}

for (const viewport of visualViewports) {
  test(`home visual baseline at ${viewport.name}`, async ({ page }) => {
    await mockVisualIdentity(page)
    await page.route('**/api/v1/feed**', route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        fingerprint: 'sha256:e2e-empty',
        freshness: 'fresh',
        generated_at: '2026-07-15T01:00:00Z',
        items: [],
        next_cursor: null,
        notices: [],
      }),
    }))
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await page.goto('/')
    await expect(page.locator('.srbg-app-shell[aria-busy="false"]')).toBeVisible({
      timeout: 20_000,
    })
    await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
    await expect(page.getByText('API v1 · Schema 1.1.0', { exact: true })).toBeVisible()
    await expect(page.getByRole('search')).toBeVisible()
    await expect(page.getByRole('region', { name: '今日重点与数据状态' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: '暂无精选内容' })).toBeVisible()
    await normalizeDynamicPageData(page)

    await expect(page).toHaveScreenshot(`home-${viewport.name}.png`, {
      animations: 'disabled',
      fullPage: true,
    })
  })
}
