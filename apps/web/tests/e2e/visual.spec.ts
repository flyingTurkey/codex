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

for (const viewport of visualViewports) {
  test(`home visual baseline at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await page.goto('/')
    await expect(page.locator('.srbg-app-shell[aria-busy="false"]')).toBeVisible({
      timeout: 20_000,
    })
    await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
    await expect(page.getByText('API v1 · Schema 1.0.0', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: '暂无精选内容' })).toBeVisible()
    await normalizeDynamicPageData(page)

    await expect(page).toHaveScreenshot(`home-${viewport.name}.png`, {
      animations: 'disabled',
      fullPage: true,
    })
  })
}
