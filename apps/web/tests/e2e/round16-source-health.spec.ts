import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('enterprise source-health console retires to owner-visible health', async ({ page }) => {
  await page.goto('/admin/source-health')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('region', { name: '来源健康通知' })).toBeVisible()
  await expect(page.getByRole('button', { name: '刷新来源健康' })).toBeVisible()
})

test('personal source health has no serious accessibility violations @a11y', async ({ page }) => {
  await page.goto('/admin/source-health')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(violation => (
    violation.impact === 'critical' || violation.impact === 'serious'
  ))).toEqual([])
})
