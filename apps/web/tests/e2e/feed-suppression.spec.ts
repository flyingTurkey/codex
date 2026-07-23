import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { v2Appendix, v2Feed, v2Projection } from './v2-fixtures'

const eventId = '019f9000-0000-7000-8000-000000000044'
const rule = {
  id: '019f9000-0000-7000-8000-000000000045',
  action: 'ACTIVATE',
  scope: 'EVENT',
  target_key: eventId,
  feedback_reason: 'OWNER_PREFERENCE',
  supersedes_rule_id: null,
  effective_at: '2026-07-23T01:00:00Z',
  created_at: '2026-07-23T01:00:00Z',
}

test('@a11y Owner confirms an Event suppression and the card leaves the Feed', async ({ page }) => {
  await page.route('**/api/v1/version', route => route.fulfill({ json: { api_version: 'v2', content_schema_version: '2.0.0' } }))
  await page.route('**/api/v1/sources', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/source-discovery/settings', route => route.fulfill({ json: { automation_enabled: false } }))
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([{
    id: eventId,
    title: '公路隧道监测更新',
    source_name: '权威来源',
    domain: 'SAFETY',
  }]) }))
  await page.route('**/api/v2/owner/suppressions', async (route) => {
    const request = route.request()
    expect(request.headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/)
    expect(request.postDataJSON()).toEqual({
      action: 'ACTIVATE', scope: 'EVENT', target_key: eventId,
      feedback_reason: 'OWNER_PREFERENCE',
    })
    await route.fulfill({ status: 201, json: rule })
  })

  await page.goto('/')
  await page.getByTestId('suppress-event').click()
  await expect(page.getByRole('alertdialog')).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: '确认隐藏' }).click()
  await expect(page.getByText('公路隧道监测更新')).toHaveCount(0)
  await expect(page.getByText('已隐藏该情报；可在“Feed 偏好”中撤销。')).toBeVisible()
})

test('@a11y Owner revokes an active suppression with concurrency headers', async ({ page }) => {
  let active = true
  await page.route('**/api/v2/owner/suppressions?**', route => route.fulfill({
    json: active ? [rule] : [],
  }))
  await page.route('**/api/v2/owner/suppressions', async (route) => {
    expect(route.request().headers()['if-match']).toBe(`"${rule.id}"`)
    expect(route.request().postDataJSON()).toMatchObject({
      action: 'REVOKE', supersedes_rule_id: rule.id,
    })
    active = false
    await route.fulfill({ status: 201, json: { ...rule, action: 'REVOKE', supersedes_rule_id: rule.id } })
  })

  await page.goto('/feed-suppressions')
  await expect(page.getByText(eventId)).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: '撤销隐藏' }).click()
  await expect(
    page.getByText('已撤销隐藏偏好；当前仍满足 PublicationService 门禁的内容会自动恢复。'),
  ).toBeVisible()
})

test('@a11y Owner can suppress the current Event from the unified reader', async ({ page }) => {
  await page.route('**/api/v1/version', route => route.fulfill({ json: { api_version: 'v2', content_schema_version: '2.0.0' } }))
  await page.route('**/api/v1/sources', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/source-discovery/settings', route => route.fulfill({ json: { automation_enabled: false } }))
  await page.route(`**/api/v2/events/${eventId}/appendix`, route => route.fulfill({ json: v2Appendix(eventId) }))
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: v2Projection({
    id: eventId, title: '公路隧道监测更新', source_name: '权威来源', domain: 'SAFETY',
  }) }))
  await page.route('**/api/v2/owner/suppressions', async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      action: 'ACTIVATE', scope: 'EVENT', target_key: eventId,
    })
    await route.fulfill({ status: 201, json: rule })
  })

  await page.goto(`/events/${eventId}`)
  await page.getByTestId('suppress-event').click()
  await expect(page.getByRole('alertdialog')).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: '确认隐藏' }).click()
  await expect(page.getByRole('status')).toContainText('已隐藏该情报')
  await expect(page.getByText('公路隧道监测更新')).toHaveCount(0)
})

test('Owner sees an explicit suppression conflict state', async ({ page }) => {
  await page.route('**/api/v2/owner/suppressions?**', route => route.fulfill({ json: [] }))
  await page.route('**/api/v2/owner/suppressions', route => route.fulfill({
    status: 412,
    json: {
      type: 'about:blank', title: 'Suppression conflict', status: 412,
      detail: { code: 'SUPPRESSION_CONFLICT', title: 'Suppression is already active' },
    },
  }))

  await page.goto('/feed-suppressions')
  await page.getByLabel('精确匹配键').fill('隧道监测')
  await page.getByRole('button', { name: '创建隐藏规则' }).click()
  await expect(page.getByRole('alert')).toContainText('相同范围与匹配键的隐藏规则已存在')
})
