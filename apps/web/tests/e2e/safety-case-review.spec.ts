import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('critical safety facts no longer expose an enterprise approval workbench', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('button', { name: '批准并发布' })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: '我的来源' })).toBeVisible()
})

test('@a11y retired safety review redirects to an accessible personal workspace', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
