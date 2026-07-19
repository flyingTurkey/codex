import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

type ProviderState = {
  keyConfigured: boolean
  runtimeStatus: string
  blockingReasons: string[]
}

async function mockAiSettings(page: Page, providerState: ProviderState = {
  keyConfigured: false,
  runtimeStatus: 'MODEL_DISABLED',
  blockingReasons: ['SECRET_NOT_CONFIGURED', 'CONFIGURATION_NOT_ACTIVE'],
}): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: 'Owner',
      local_identity: true,
      roles: ['owner'],
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
  await page.route('**/api/v1/settings/ai/providers', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      code: 'deepseek',
      base_url: 'https://api.deepseek.com',
      request_path: '/chat/completions',
      models: ['deepseek-v4-flash'],
      real_call_enabled: true,
      key_configured: providerState.keyConfigured,
      runtime_status: providerState.runtimeStatus,
      blocking_reasons: providerState.blockingReasons,
      token_limits: { CLASSIFY: 1200, EXTRACT: 4000 },
      budget: { monthly_points: 20000, document_points: 100 },
    }]),
  }))
}

test('saving a Secret confirms configuration without manufacturing runtime readiness', async ({ page }) => {
  const providerState: ProviderState = {
    keyConfigured: false,
    runtimeStatus: 'MODEL_DISABLED',
    blockingReasons: ['SECRET_NOT_CONFIGURED'],
  }
  await mockAiSettings(page, providerState)
  await page.route('**/api/v1/settings/ai/providers/deepseek/secret', (route) => {
    providerState.keyConfigured = true
    providerState.runtimeStatus = 'UNKNOWN'
    providerState.blockingReasons = ['AI_RUNTIME_WINDOW_INCOMPLETE']
    return route.fulfill({ status: 204 })
  })
  await page.goto('/settings/ai')
  await page.getByLabel('写入 Secret').fill('test-only-secret')
  await page.getByRole('button', { name: '保存 Secret' }).click()
  await expect(page.getByRole('status')).toContainText('配置成功')
  await expect(page.getByLabel('写入 Secret')).toHaveValue('')
  await expect(page.getByRole('definition').filter({ hasText: '已配置' })).toBeVisible()
  await expect(page.getByRole('definition').filter({ hasText: '不可用（UNKNOWN）' })).toBeVisible()
})

test('a failed Secret save shows an error popup and keeps the value for retry', async ({ page }) => {
  await mockAiSettings(page)
  await page.route('**/api/v1/settings/ai/providers/deepseek/secret', route => route.fulfill({
    status: 500,
    contentType: 'application/problem+json',
    body: JSON.stringify({ title: 'Secret 保存失败', detail: '私有存储暂不可写。' }),
  }))
  await page.goto('/settings/ai')
  await page.getByLabel('写入 Secret').fill('test-only-secret')
  await page.getByRole('button', { name: '保存 Secret' }).click()
  await expect(page.getByRole('alert')).toContainText('保存失败')
  await expect(page.getByLabel('写入 Secret')).toHaveValue('test-only-secret')
})

test('personal AI settings show the pinned endpoint and no arbitrary URL control', async ({ page }) => {
  await mockAiSettings(page)
  await page.goto('/settings/ai')
  await expect(page.getByRole('heading', { name: 'AI 模型配置' })).toBeVisible()
  await expect(page.getByText('https://api.deepseek.com/chat/completions')).toBeVisible()
  await expect(page.locator('input[name="base_url"]')).toHaveCount(0)
  await expect(page.getByLabel('写入 Secret')).toHaveAttribute('type', 'password')
})

test('@a11y personal AI settings have no axe violations', async ({ page }) => {
  await mockAiSettings(page)
  await page.goto('/settings/ai')
  await expect(page.getByRole('heading', { name: 'AI 模型配置' })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
