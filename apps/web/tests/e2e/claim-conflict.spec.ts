import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('human claim conflict review retires to the personal source workspace', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('heading', { level: 1, name: '我的来源' })).toBeVisible()
  await expect(page.getByText('关键字段冲突')).toHaveCount(0)
})

test('@a11y retired claim review redirects to an accessible personal workspace', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
