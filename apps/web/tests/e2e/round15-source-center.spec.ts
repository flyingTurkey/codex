import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('legacy source center routes converge on owner URL detection and runtime state', async ({ page }) => {
  for (const path of [
    '/admin/sources',
    '/admin/sources/019b0000-0000-7000-8000-000000000001',
    '/admin/sources/coverage',
  ]) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
    await expect(page.getByRole('heading', { level: 1, name: '我的来源' })).toBeVisible()
    await expect(page.getByRole('form', { name: '添加公开来源 URL' })).toBeVisible()
    await expect(page.getByText('生产批准')).toHaveCount(0)
    await expect(page.getByText('资格通过')).toHaveCount(0)
  }
})

test('owner source workspace keeps legacy controls absent and is accessible @a11y', async ({ page }) => {
  await page.goto('/sources')
  await expect(page.getByRole('button', { name: '保存并探测' })).toBeVisible()
  await expect(page.getByRole('button', { name: '批准生产' })).toHaveCount(0)
  await expect(page.getByText('人工复核')).toHaveCount(0)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
