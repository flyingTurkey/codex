import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockAiAdmin(page: Page): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: '平台管理员',
      local_identity: true,
      roles: ['platform_admin'],
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
  await page.route('**/api/v1/admin/ai/providers', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      code: 'deepseek',
      base_url: 'https://api.deepseek.com',
      request_path: '/chat/completions',
      models: ['deepseek-v4-flash'],
      real_call_enabled: true,
      key_configured: false,
      runtime_status: 'MODEL_DISABLED',
      blocking_reasons: ['SECRET_NOT_CONFIGURED', 'CONFIGURATION_NOT_ACTIVE'],
      token_limits: { CLASSIFY: 1200, EXTRACT: 4000 },
      budget: { monthly_points: 20000, document_points: 100 },
    }]),
  }))
}

test('R-AI01 admin shows the pinned endpoint and no arbitrary URL control', async ({ page }) => {
  await mockAiAdmin(page)
  await page.goto('/admin/ai')
  await expect(page.getByRole('heading', { name: 'AI 模型配置' })).toBeVisible()
  await expect(page.getByText('https://api.deepseek.com/chat/completions')).toBeVisible()
  await expect(page.locator('input[name="base_url"]')).toHaveCount(0)
  await expect(page.getByLabel('写入 Secret')).toHaveAttribute('type', 'password')
})

test('@a11y R-AI01 model administration has no axe violations', async ({ page }) => {
  await mockAiAdmin(page)
  await page.goto('/admin/ai')
  await expect(page.getByRole('heading', { name: 'AI 模型配置' })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
