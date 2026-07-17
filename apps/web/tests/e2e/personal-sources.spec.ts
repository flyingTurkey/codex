import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const sourceId = '019b0000-0000-7000-8000-000000000001'

async function mockPersonalSources(page: Page): Promise<void> {
  const source = {
    id: sourceId,
    display_name: '交通运输部',
    url: 'https://www.mot.gov.cn/',
    desired_enabled: true,
    runtime_state: 'PENDING_CONFIGURATION',
    manual_disabled_at: null,
    normalized_origin: 'https://www.mot.gov.cn/',
    streams: [],
    latest_probe_run: null,
  }
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      user_id: '019b0000-0000-7000-8000-000000009001',
      display_name: '本地个人 Owner',
      roles: ['owner', 'viewer'],
      local_identity: true,
    }),
  }))
  await page.route(`**/api/v1/sources/${sourceId}`, async (route) => {
    const body = route.request().postDataJSON() as { desired_enabled: boolean }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ...source,
        desired_enabled: body.desired_enabled,
        manual_disabled_at: body.desired_enabled ? null : '2026-07-17T10:00:00Z',
      }),
    })
  })
  await page.route('**/api/v1/sources', route => route.fulfill({
    status: route.request().method() === 'POST' ? 202 : 200,
    contentType: 'application/json',
    body: JSON.stringify(route.request().method() === 'POST'
      ? {
          ...source,
          streams: [{
            id: '019b0000-0000-7000-8000-000000000111',
            stream_type: 'UNKNOWN',
            normalized_url: 'https://www.mot.gov.cn/',
            allowed_hosts: ['www.mot.gov.cn'],
            config_sha256: null,
            discovery_method: 'MANUAL_URL',
            status: 'PROBING',
            failure_reason: null,
          }],
          latest_probe_run: {
            id: '019b0000-0000-7000-8000-000000000112',
            requested_url: 'https://www.mot.gov.cn/',
            input_kind: 'UNKNOWN',
            status: 'QUEUED',
            duration_ms: null,
            failure_code: null,
            failure_reason: null,
          },
        }
      : [source]),
  }))
  const profile = {
    snapshot_id: '019b0000-0000-7000-8000-000000000201', version: 1,
    status: 'PARTIAL', overall_confidence: 70, overridden_fields: [],
    automatic: { industries: ['HIGHWAY'], content_domains: ['SAFETY_REGULATION'], language_tags: ['zh-CN'], country_codes: ['CN'], region_codes: [], declared_roles: ['OFFICIAL_PRIMARY'], authority_level: 'A0', independence_level: 'NOT_INDEPENDENT' },
    effective: { industries: ['HIGHWAY'], content_domains: ['SAFETY_REGULATION'], language_tags: ['zh-CN'], country_codes: ['CN'], region_codes: [], declared_roles: ['OFFICIAL_PRIMARY'], authority_level: 'A0', independence_level: 'NOT_INDEPENDENT' },
    field_explanations: Object.fromEntries(['industries', 'content_domains', 'language_tags', 'country_codes', 'region_codes', 'declared_roles', 'authority_level', 'independence_level'].map(field => [field, { confidence: field === 'region_codes' ? 0 : 85, reason_codes: ['DETERMINISTIC_SOURCE_EVIDENCE'], evidence_ids: ['home'], basis: 'AUTO_INFERRED' }])),
    evidence: [{ evidence_id: 'home', kind: 'HOMEPAGE', url: 'https://www.mot.gov.cn/', sha256: 'a'.repeat(64), excerpt: '交通运输部公路安全栏目' }],
    technical_facts: ['RSS_ATOM'], reason_codes: ['PROFILE_EVIDENCE_PARTIAL'],
    rule_version: 'source-profile-rules-v1', prompt_version: 'source-profile-prompt-v1', schema_version: 'source-profile-output-v1', model_version: 'deepseek-v4-flash', input_sha256: 'b'.repeat(64), generated_at: '2026-07-17T00:00:00Z',
  }
  await page.route(`**/api/v1/sources/${sourceId}/profile`, route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify(profile),
  }))
  await page.route(`**/api/v1/sources/${sourceId}/profile-override`, route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify(route.request().method() === 'DELETE' ? profile : { ...profile, overridden_fields: ['industries'] }),
  }))
}

for (const viewport of [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  test(`personal sources keeps intent and runtime distinct on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockPersonalSources(page)
    await page.goto('/sources')

    await expect(page.getByRole('heading', { name: '我的来源' })).toBeVisible()
    await expect(page.getByText('用户已启用')).toBeVisible()
    await expect(page.getByText('待自动配置')).toBeVisible()
    await expect(page.getByText('当前正在运行')).toHaveCount(0)

    await page.getByRole('switch', { name: '停用交通运输部' }).click()
    await expect(page.getByText('用户已停用')).toBeVisible()
    await expect(page.getByText('待自动配置')).toBeVisible()
  })
}

test('@a11y personal sources has no axe violations', async ({ page }) => {
  await mockPersonalSources(page)
  await page.goto('/sources')

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})

test('owner can add one public URL and sees probe feedback', async ({ page }) => {
  await mockPersonalSources(page)
  await page.goto('/sources')

  await page.getByLabel('添加 URL').fill('https://www.mot.gov.cn/')
  await page.getByRole('button', { name: '保存并探测' }).click()

  await expect(page.getByRole('status')).toContainText('URL 已保存')
})

test('owner sees automatic evidence and can distinguish personal override', async ({ page }) => {
  await mockPersonalSources(page)
  await page.goto('/sources')
  await page.getByRole('button', { name: '查看画像' }).click()
  const drawer = page.getByRole('dialog', { name: /自动画像/ })
  await expect(drawer.getByText('总体置信度', { exact: false })).toBeVisible()
  await expect(drawer.getByText('自动结果', { exact: false }).first()).toBeVisible()
  await expect(drawer).not.toContainText('人工复核')
})
