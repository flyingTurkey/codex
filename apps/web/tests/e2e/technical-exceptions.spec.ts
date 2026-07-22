import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const exception = {
  id: '019f8900-0000-7000-8000-000000000043',
  kind: 'TECHNICAL',
  status: 'OPEN',
  overrideability: null,
  source_id: '019f8900-0000-7000-8000-000000000041',
  source_stream_id: '019f8900-0000-7000-8000-000000000042',
  document_version_id: '019f8900-0000-7000-8000-000000000044',
  decision_id: '019f8900-0000-7000-8000-000000000045',
  reason_codes: ['TECHNICAL_EXHAUSTED'],
  technical_reason_code: 'PROVIDER_TIMEOUT',
  attempt_count: 4,
  version: 1,
  opened_at: '2026-07-22T02:00:00Z',
  updated_at: '2026-07-22T02:30:00Z',
  resolved_at: null,
}

async function mockTechnicalExceptions(page: Page): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: 'Owner', local_identity: true, roles: ['owner'],
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
  await page.route('**/api/v2/owner/exceptions?**', route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify([exception]),
  }))
}

test('Owner retries once and can disable the affected source', async ({ page }) => {
  await mockTechnicalExceptions(page)
  let retryRequests = 0
  await page.route(`**/api/v2/owner/exceptions/${exception.id}/commands`, async (route) => {
    retryRequests += 1
    const request = route.request()
    expect(request.headers()['if-match']).toBe('"1"')
    expect(request.headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/)
    expect(request.postDataJSON()).toEqual({
      exception_id: exception.id, event_type: 'RETRY_REQUESTED', expected_version: 1,
    })
    await route.fulfill({ status: 202, contentType: 'application/json', body: '{}' })
  })
  await page.route(`**/api/v1/sources/${exception.source_id}`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ desired_enabled: false })
    await route.fulfill({ contentType: 'application/json', body: '{}' })
  })

  await page.goto('/technical-exceptions')
  await expect(page.getByRole('heading', { name: '技术异常' })).toBeVisible()
  await expect(page.getByText('PROVIDER_TIMEOUT')).toBeVisible()
  await page.getByRole('button', { name: '立即重试' }).dblclick()
  await expect(page.getByText('已记录立即重试请求，后台将从耐久状态恢复。')).toBeVisible()
  expect(retryRequests).toBe(1)
  await page.getByRole('button', { name: '停用来源' }).click()
  await expect(page.getByText(/^已记录停用来源/)).toBeVisible()
})

test('technical exception workspace reflows at a 200% equivalent viewport', async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 900 })
  await mockTechnicalExceptions(page)
  await page.goto('/technical-exceptions')

  await expect(page.getByRole('heading', { name: '技术异常' })).toBeVisible()
  await expect(page.getByRole('button', { name: '立即重试' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => document.documentElement.clientWidth),
  )
})

test('@a11y technical exception workspace has no axe violations', async ({ page }) => {
  await mockTechnicalExceptions(page)
  await page.goto('/technical-exceptions')
  await expect(page.getByRole('heading', { name: '技术异常' })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
