import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('enterprise source candidate form retires to owner URL detection', async ({ page }) => {
  await page.goto('/admin/sources/new')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  await expect(page.getByRole('form', { name: '添加公开来源 URL' })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存并探测' })).toBeVisible()
  await expect(page.getByText('服务端资格包')).toHaveCount(0)
})

test('@a11y retired source registry redirects to an accessible owner workspace', async ({ page }) => {
  await page.goto('/admin/sources')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
