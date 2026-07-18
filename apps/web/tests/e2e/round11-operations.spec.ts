import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockOwner(page: Page): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    json: {
      display_name: 'Owner',
      local_identity: true,
      roles: ['owner'],
      user_id: '019b0000-0000-7000-8000-000000000011',
    },
  }))
  await page.route('**/api/v1/sources', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/source-discovery/**', route => route.fulfill({
    json: route.request().url().includes('/topics') ? [] : {},
  }))
}

test('enterprise operations pages are unavailable and absent from personal navigation', async ({ page }) => {
  await mockOwner(page)
  const response = await page.goto('/admin/operations')
  expect(response?.status()).toBe(404)
  await expect(page.getByRole('heading', { level: 1, name: '404' })).toBeVisible()

  await page.goto('/sources')
  await expect(page.getByRole('heading', { level: 1, name: '我的来源' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'AI 模型配置' })).toBeVisible()
  await expect(page.getByRole('link', { name: '运行中心' })).toHaveCount(0)
})

test('@a11y personal operational surfaces support keyboard and 200% equivalent viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 720, height: 450 })
  await mockOwner(page)
  await page.goto('/sources')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(720)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
