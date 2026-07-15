import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const itemId = '019b0000-0000-7000-8000-000000007201'
const evidenceId = '019b0000-0000-7000-8000-000000007211'
const item = {
  activity_at: '2026-07-15T04:00:00Z',
  content_type: 'LOW_ALTITUDE_EQUIPMENT',
  domain: 'DIGITAL',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-15T04:05:00Z',
  id: itemId,
  original_url: 'https://enterprise.dji.com/cn/example',
  publication_revision_id: '019b0000-0000-7000-8000-000000007202',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '大疆行业应用',
  source_published_at: '2026-05-01T00:00:00Z',
  source_role: '厂商一手来源',
  title: '经纬 M350 RTK 无人机平台',
  type_summary: {
    evidence_level: 'VENDOR_CLAIM_ONLY',
    kind: 'LOW_ALTITUDE_EQUIPMENT',
    model_no: 'M350 RTK',
    payload_types: ['可见光相机'],
    permit_status: 'UNKNOWN',
    platform_type: '多旋翼无人机',
    product_kind: 'LOW_ALTITUDE_EQUIPMENT',
    product_name: '经纬 350 RTK',
    promotional_claim_count: 1,
    vendor_name: '深圳市大疆创新科技有限公司',
    verified_capability_count: 0,
    version: 'V1.0',
  },
}
const technologyProduct = {
  application_scenarios: ['INSPECTION'],
  current_version: 'V1.0',
  deployment_modes: ['ON_DEVICE'],
  engineering_cases: [],
  evidence_level: 'VENDOR_CLAIM_ONLY',
  interfaces: ['SDK'],
  limitations: ['使用前需核验项目现场与监管要求'],
  low_altitude_notice: '产品发布不代表空域、适航、飞手和项目许可。',
  model: { id: '019b0000-0000-7000-8000-000000007204', name: 'M350 RTK' },
  permit_status: 'UNKNOWN',
  procurement_notice: '仅供技术调研，不构成采购建议',
  product: { id: '019b0000-0000-7000-8000-000000007205', name: '经纬 350 RTK' },
  product_kind: 'LOW_ALTITUDE_EQUIPMENT',
  promotional_claims: [{
    attribution: '深圳市大疆创新科技有限公司',
    claim_id: '019b0000-0000-7000-8000-000000007206',
    evidence_ids: [evidenceId],
    independent_evidence_ids: [],
    kind: 'PROMOTIONAL_CLAIM',
    statement: '支持多载荷任务配置',
  }],
  vendor: { id: '019b0000-0000-7000-8000-000000007207', name: '深圳市大疆创新科技有限公司' },
  verified_capabilities: [],
  version_history: ['V1.0'],
}

async function mockProduct(page: Page): Promise<void> {
  await page.route('**/api/v1/feed**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      fingerprint: 'sha256:round07-e2e', freshness: 'fresh',
      generated_at: '2026-07-15T04:10:00Z', items: [item], next_cursor: null, notices: [],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ item, claims: [], evidence: [], technology_product: technologyProduct }),
  }))
}

test('four product tabs reuse the digital feed and expose product filters', async ({ page }) => {
  await mockProduct(page)
  await page.goto('/digital')
  await page.getByRole('button', { name: '低空设备' }).click()

  await expect(page.getByRole('heading', { level: 1, name: '技术产品' })).toBeVisible()
  await expect(page.getByTestId('product-summary')).toContainText('M350 RTK / V1.0')
  await expect(page.getByText('许可状态未知')).toBeVisible()
  await page.getByLabel('证据等级').selectOption('VENDOR_CLAIM_ONLY')
  await page.getByLabel('部署方式').selectOption('ON_DEVICE')
})

test('@a11y product detail separates capabilities evidence and permits without axe violations', async ({ page }) => {
  await mockProduct(page)
  await page.goto(`/items/${itemId}`)

  await expect(page.getByRole('heading', { level: 1, name: '技术产品详情' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '产品能力' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '工程证据' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '许可与限制' })).toBeVisible()
  await expect(
    page.locator('.item-detail-page__permit-boundary'),
  ).toHaveText('产品发布不代表空域、适航、飞手和项目许可。')
  await expect(page.getByText('仅供技术调研，不构成采购建议')).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
