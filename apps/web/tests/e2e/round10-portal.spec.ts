import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const itemId = '019b1000-0000-7000-8000-000000000001'
const revisionId = '019b1000-0000-7000-8000-000000000002'
const reportId = '019b1000-0000-7000-8000-000000000003'
const evidenceId = '019b1000-0000-7000-8000-000000000004'
const claimId = '019b1000-0000-7000-8000-000000000005'

const resultItem = {
  activity_at: '2026-07-15T01:00:00Z',
  content_type: 'SAFETY_REGULATION',
  domain: 'SAFETY',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-15T01:00:00Z',
  id: itemId,
  original_url: 'https://jtyst.sc.gov.cn/example',
  publication_revision_id: revisionId,
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  search_context: {
    match_kind: 'EXACT_IDENTIFIER',
    matched_fields: ['DOCUMENT_NUMBER'],
    matched_identifiers: ['川交规〔2026〕10号'],
    semantic_status: 'DEGRADED',
  },
  source_name: '四川省交通运输厅',
  source_published_at: '2026-07-15T00:30:00Z',
  source_role: '官方一手来源',
  title: '四川公路隧道监测预警工作指引',
  type_summary: {
    classification: 'STANDARD_OR_GUIDE',
    document_number: '川交规〔2026〕10号',
    issuing_authority: '四川省交通运输厅',
    kind: 'SAFETY_REGULATION',
    regulation_status: 'UNKNOWN',
  },
} as const

function feed(items: unknown[]) {
  return {
    fingerprint: 'search:10',
    freshness: 'fresh',
    generated_at: '2026-07-15T01:05:00Z',
    items,
    next_cursor: null,
    notices: [{
      code: 'SEMANTIC_SEARCH_DEGRADED',
      level: 'warning',
      message: '语义召回暂不可用，当前结果来自精确编号和关键词检索。',
    }],
  }
}

async function mockRound10Api(page: Page): Promise<void> {
  await page.route('**/api/v1/search**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(feed([resultItem])),
  }))
  await page.route(`**/api/v1/items/${itemId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      item: resultItem,
      claims: [{
        claim_type: 'document_number',
        evidence_ids: [evidenceId],
        id: claimId,
        label: '文号',
        value: '川交规〔2026〕10号',
      }],
      evidence: [{
        char_end: 14,
        char_start: 0,
        claim_ids: [claimId],
        excerpt: '川交规〔2026〕10号',
        excerpt_sha256: 'a'.repeat(64),
        id: evidenceId,
        original_url: resultItem.original_url,
        paragraph_id: 'html-p-0010',
      }],
    }),
  }))
  await page.route('**/api/v1/saved-events', route => route.fulfill({ status: 204 }))
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: '演示用户',
      roles: ['viewer'],
      user_id: '019b1000-0000-7000-8000-000000000099',
    }),
  }))
  await page.route('**/api/v1/daily', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      id: reportId,
      published_at: '2026-07-15T01:10:00Z',
      report_date: '2026-07-15',
      requires_regeneration: false,
      sections: [{
        items: [{
          current_state: 'PUBLISHED',
          item_id: itemId,
          original_url: resultItem.original_url,
          position: 1,
          publication_revision_id: revisionId,
          summary: '围绕公路隧道监测预警建立分级处置要求。',
          title: resultItem.title,
        }],
        kind: 'TODAY_HIGHLIGHTS',
        title: '今日重点',
      }],
      snapshot_at: '2026-07-15T01:00:00Z',
      status: 'PUBLISHED',
    }),
  }))
}

test('exact search opens evidence, saves the item, and reaches the published daily', async ({
  page,
}) => {
  await mockRound10Api(page)
  await page.goto('/search?q=%E5%B7%9D%E4%BA%A4%E8%A7%84%E3%80%942026%E3%80%9510%E5%8F%B7')

  await expect(page.getByRole('heading', { level: 1, name: '搜索' })).toBeVisible()
  await expect(page.getByText('精确编号命中', { exact: true })).toBeVisible()
  await expect(page.getByText('川交规〔2026〕10号', { exact: true })).toBeVisible()

  await page.getByTestId('evidence-trigger').click()
  await expect(page.getByRole('dialog', { name: '原文段落与页码定位' })).toContainText(
    'html-p-0010',
  )
  await page.keyboard.press('Escape')

  const saveButton = page.getByRole('button', { name: '收藏', exact: true })
  await saveButton.click()
  await expect(page.getByRole('button', { name: '已收藏', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )

  await page.getByRole('link', { name: '行业日报', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '行业日报' })).toBeVisible()
  await expect(page.getByText('已审核发布', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: '今日重点' })).toBeVisible()
  await expect(page.getByText('围绕公路隧道监测预警建立分级处置要求。')).toBeVisible()
  await expect(page.getByRole('button', { name: '生成今日草稿' })).toHaveCount(0)
})

test('@a11y search and daily remain readable at 768px without axe violations', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await mockRound10Api(page)

  for (const path of ['/search?q=%E5%B7%9D%E4%BA%A4%E8%A7%84%E3%80%942026%E3%80%9510%E5%8F%B7', '/daily']) {
    await page.goto(path)
    await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
      timeout: 15_000,
    })
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768)
  }
})
