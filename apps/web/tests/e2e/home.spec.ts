import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('renders the demo intelligence overview without browser errors', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1, name: '今日情报概览' })).toBeVisible()
  await expect(page.getByText('演示环境', { exact: true })).toBeVisible()
  await expect(page.getByText('API v1 · Schema 1.0.0', { exact: true })).toBeVisible()
  await expect(page.getByTestId('metric')).toHaveCount(4)
  await expect(page.getByRole('heading', { level: 2, name: '数字化精选' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '安全重点' })).toBeVisible()
  expect(consoleErrors).toEqual([])
})

test('@a11y homepage has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: '今日情报概览' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
