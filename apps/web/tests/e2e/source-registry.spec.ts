import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('source admin registers a default-denied candidate and opens admission tools', async ({ page }) => {
  await page.goto('/admin/sources')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  await expect(page.getByRole('heading', { level: 1, name: '来源注册与准入' })).toBeVisible()
  await expect(page.getByText('默认拒绝', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '登记候选来源', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '登记候选来源' })
  await expect(drawer).toBeVisible()
  const unique = Date.now().toString()
  const sourceName = `浏览器验收来源-${unique}`
  await drawer.getByLabel('来源名称').fill(sourceName)
  await drawer.getByLabel('来源 URL').fill(`https://example.test/e2e/${unique}`)
  await drawer.getByRole('button', { name: '登记候选来源' }).click()

  await expect(page).toHaveURL(/\/admin\/sources\/[0-9a-f-]+$/)
  await expect(page.getByRole('heading', { level: 1, name: sourceName })).toBeVisible()
  const detailPage = page.locator('.source-detail-page')
  await expect(detailPage.getByText('候选', { exact: true })).toBeVisible()
  await expect(detailPage.getByText(/disabled · 0\/30 样本/)).toBeVisible()

  await page.getByRole('button', { name: '准入策略' }).click()
  const policyDrawer = page.getByRole('dialog', { name: '来源准入策略' })
  await expect(policyDrawer).toBeVisible()
  await policyDrawer.getByRole('button', { name: '关闭抽屉' }).click()

  await page.getByRole('button', { name: '准入记录' }).click()
  const onboardingDrawer = page.getByRole('dialog', { name: '来源准入记录' })
  await expect(onboardingDrawer).toBeVisible()
  await onboardingDrawer.getByRole('button', { name: '关闭抽屉' }).click()

  await page.getByRole('button', { name: '上传样本' }).click()
  await expect(page.getByRole('dialog', { name: '上传固定样本' })).toBeVisible()
  await expect(page.getByText(/仅允许 HTML\/PDF，最大 50 MiB/)).toBeVisible()
})

test('@a11y source registry list has no axe violations', async ({ page }) => {
  await page.goto('/admin/sources')
  await expect(page.getByRole('heading', { level: 1, name: '来源注册与准入' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
