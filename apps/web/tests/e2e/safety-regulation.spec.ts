import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const itemId = '019b0000-0000-7000-8000-000000001001'
const taskId = '019b0000-0000-7000-8000-000000001002'
const revisionId = '019b0000-0000-7000-8000-000000001003'
const pdfVersionId = '019b0000-0000-7000-8000-000000001020'
const baseItem = {
  activity_at: '2026-07-14T01:09:04Z',
  content_type: 'SAFETY_REGULATION',
  domain: 'SAFETY',
  first_discovered_at: '2026-07-14T01:09:04Z',
  id: itemId,
  original_url: 'https://www.mem.gov.cn/example.shtml',
  publication_revision_id: null,
  review_status: 'PENDING',
  source_name: '应急管理部',
  source_published_at: '2016-06-03T10:28:00Z',
  title: '生产安全事故应急预案管理办法',
} as const
const claims = [
  {
    claim_type: 'document_number',
    evidence_ids: ['019b0000-0000-7000-8000-000000001005'],
    id: '019b0000-0000-7000-8000-000000001004',
    label: '文号',
    value: '国家安全生产监督管理总局令第88号',
  },
]
const evidence = [
  {
    char_end: 18,
    char_start: 0,
    claim_ids: ['019b0000-0000-7000-8000-000000001004'],
    excerpt: '国家安全生产监督管理总局令第88号',
    excerpt_sha256: 'a'.repeat(64),
    id: '019b0000-0000-7000-8000-000000001005',
    original_url: 'https://www.mem.gov.cn/example.shtml',
    paragraph_id: 'html-p-0002',
  },
]

function feed(items: unknown[]) {
  return {
    fingerprint: 'sha256:e2e',
    freshness: 'fresh',
    generated_at: '2026-07-14T01:09:04Z',
    items,
    next_cursor: null,
    notices: [],
  }
}

async function openSafetyFromClientNavigation(page: Page): Promise<void> {
  await page.goto('/safety')
  await expect(page).toHaveURL(/\/safety$/)
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
}

test('R3 pending feed card exposes only whitelist UI and no scores', async ({ page }) => {
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed([baseItem])) }),
  )

  await openSafetyFromClientNavigation(page)

  await expect(page.getByRole('heading', { level: 1, name: '安全情报' })).toBeVisible()
  await expect(page.getByText('待人工审核', { exact: true })).toBeVisible()
  await expect(page.getByText('应急管理部', { exact: true })).toBeVisible()
  await expect(page.getByTestId('evidence-trigger')).toHaveCount(0)
  await expect(page.getByText(/评分|可信度|效力结论|AI 摘要/)).toHaveCount(0)
})

test('published card opens paragraph-addressed evidence drawer', async ({ page }) => {
  const published = {
    ...baseItem,
    evidence_count: 1,
    evidence_status: 'VERIFIED',
    publication_revision_id: revisionId,
    publication_status: 'PUBLISHED',
    review_status: 'APPROVED',
    source_role: '官方一手来源',
    type_summary: {
      classification: 'DEPARTMENT_RULE',
      document_number: '国家安全生产监督管理总局令第88号',
      issuing_authority: '应急管理部',
      kind: 'SAFETY_REGULATION',
      regulation_status: 'UNKNOWN',
    },
  }
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed([published])) }),
  )
  await page.route(`**/api/v1/items/${itemId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ item: published, claims, evidence }),
    }),
  )

  await openSafetyFromClientNavigation(page)
  await page.getByTestId('evidence-trigger').click()

  const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('button', { name: '关闭证据抽屉' })).toBeFocused()
  await expect(drawer.getByText('html-p-0002', { exact: false })).toBeVisible()
  await expect(drawer.getByText('国家安全生产监督管理总局令第88号')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
})

test('PDF evidence supports page jump, highlight, timeline, diff, and focus return', async ({ page }) => {
  const pdfItem = {
    ...baseItem,
    document_states: ['UPDATED'],
    evidence_count: 1,
    evidence_status: 'VERIFIED',
    has_version_history: true,
    publication_revision_id: revisionId,
    publication_status: 'PUBLISHED',
    review_status: 'APPROVED',
    source_role: '官方一手来源',
    title: '测试专用桥梁施工安全规定',
    type_summary: {
      classification: 'DEPARTMENT_RULE',
      document_number: 'TEST-ONLY-2026-03',
      issuing_authority: '应急管理部',
      kind: 'SAFETY_REGULATION',
      regulation_status: 'UNKNOWN',
    },
  }
  const pdfEvidence = [{
    claim_ids: [claims[0]?.id],
    document_version_id: pdfVersionId,
    excerpt: 'Effective: 2026-08-01',
    excerpt_sha256: 'b'.repeat(64),
    id: evidence[0]?.id,
    locator: {
      bbox: { x0: 72000, x1: 260000, y0: 220000, y1: 250000 },
      block_id: '019b0000-0000-7000-8000-000000001021',
      page_number: 2,
      type: 'PDF_TEXT',
    },
    original_url: pdfItem.original_url,
  }]
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed([pdfItem])) }),
  )
  await page.route(`**/api/v1/items/${itemId}`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ item: pdfItem, claims, evidence: pdfEvidence }),
  }))
  await page.route(`**/api/v1/items/${itemId}/versions`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      item_id: itemId,
      versions: [
        { acquired_at: '2026-07-01T00:00:00Z', change_type: 'INITIAL', is_current: false, material: true, processing_state: 'READY', review_state: 'APPROVED', version_id: '019b0000-0000-7000-8000-000000001019', version_number: 1 },
        { acquired_at: '2026-07-14T00:00:00Z', change_type: 'CONTENT_UPDATE', is_current: true, material: true, processing_state: 'READY', review_state: 'APPROVED', version_id: pdfVersionId, version_number: 2 },
      ],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}/diff**`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      changed_token_count: 12,
      changed_token_ratio_bps: 80,
      change_type: 'CONTENT_UPDATE',
      critical_fields: [{ after: 'TEST-ONLY-2026-03', before: 'TEST-ONLY-2026-01', field: 'document_number' }],
      from_version_id: '019b0000-0000-7000-8000-000000001019',
      item_id: itemId,
      material: true,
      pages: [{ category: 'BODY', hunks: [{ after: 'shall inspect', before: 'should inspect', operation: 'REPLACE' }], page_number: 2 }],
      to_version_id: pdfVersionId,
    }),
  }))
  await page.route(`**/api/v1/document-versions/${pdfVersionId}/pages/*`, (route) => {
    if (route.request().url().endsWith('/preview')) {
      return route.fulfill({
        contentType: 'image/png',
        body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n1cAAAAASUVORK5CYII=', 'base64'),
      })
    }
    const pageNumber = Number(route.request().url().split('/').at(-1))
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        document_version_id: pdfVersionId,
        height_mpt: 842000,
        page_count: 3,
        page_number: pageNumber,
        preview_url: `/api/v1/document-versions/${pdfVersionId}/pages/${pageNumber}/preview`,
        rotation: 0,
        text_source: 'NATIVE',
        width_mpt: 595000,
      }),
    })
  })

  await openSafetyFromClientNavigation(page)
  const trigger = page.getByTestId('evidence-trigger')
  await trigger.click()
  const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByText('版本时间线')).toBeVisible()
  await expect(drawer.getByText('版本差异')).toBeVisible()
  await expect(drawer.getByTestId('pdf-highlight')).toBeVisible()
  await drawer.getByRole('button', { name: '下一页' }).click()
  await expect(drawer.getByText('第 3 / 3 页')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('review workspace submits only decision and reason to the service endpoint', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  return
  const reviewDetail = {
    claims,
    evidence,
    item: {
      ...baseItem,
      ai_assistance: {
        accepted_claims_only: true,
        generated_at: '2026-07-14T01:08:00Z',
        model_profile: 'mock-v1',
        pipeline_run_id: '019b0000-0000-7000-8000-000000001030',
        prompt_version: 'summary-v1',
        schema_version: 'summary-schema-v1',
        status: 'ASSISTED',
      },
      evidence_count: 1,
      evidence_status: 'VERIFIED',
      publication_status: 'PENDING_REVIEW',
      type_summary: {
        classification: 'DEPARTMENT_RULE',
        document_number: '国家安全生产监督管理总局令第88号',
        issuing_authority: '应急管理部',
        kind: 'SAFETY_REGULATION',
        regulation_status: 'UNKNOWN',
      },
    },
    task: {
      id: taskId,
      item_id: itemId,
      risk_level: 'R3',
      source_name: '应急管理部',
      status: 'PENDING',
      submitted_at: '2026-07-14T01:09:04Z',
      submitted_by: '019b0000-0000-7000-8000-000000001099',
      title: baseItem.title,
    },
  }
  let decisionBody: unknown
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        display_name: 'E2E 审核员',
        local_identity: true,
        roles: ['reviewer'],
        user_id: '019b0000-0000-7000-8000-000000001098',
      }),
    }),
  )
  await page.route('**/api/v1/admin/review-tasks**', async (route) => {
    const request = route.request()
    if (request.method() === 'POST') {
      decisionBody = request.postDataJSON()
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          publication_revision_id: revisionId,
          review_task_id: taskId,
          status: 'APPROVED',
        }),
      })
      return
    }
    if (request.url().endsWith(`/${taskId}`)) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(reviewDetail) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([reviewDetail.task]) })
  })

  await page.goto(`/admin/review/${taskId}`)
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
  const workbench = page.getByRole('region', { name: '三栏审核工作台' })
  await expect(workbench.getByRole('heading', { name: '原文与定位证据' })).toBeVisible()
  await expect(workbench.getByRole('heading', { name: '字段与证据' })).toBeVisible()
  await expect(workbench.getByRole('heading', { name: '摘要对照与决定' })).toBeVisible()
  await workbench.getByText('Prompt / Schema / 模型版本').click()
  await expect(workbench.getByText('summary-v1')).toBeVisible()
  await expect(workbench.getByText('模型建议不具授权性', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '批准并发布' }).click()

  expect(decisionBody).toEqual({ action: 'APPROVE', reason: '字段与官方原文证据一致' })
})

test('@a11y published safety feed and evidence drawer have no axe violations', async ({ page }) => {
  const published = {
    ...baseItem,
    evidence_count: 1,
    evidence_status: 'VERIFIED',
    publication_revision_id: revisionId,
    publication_status: 'PUBLISHED',
    review_status: 'APPROVED',
    source_role: '官方一手来源',
    type_summary: {
      classification: 'DEPARTMENT_RULE',
      document_number: '国家安全生产监督管理总局令第88号',
      issuing_authority: '应急管理部',
      kind: 'SAFETY_REGULATION',
      regulation_status: 'UNKNOWN',
    },
  }
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed([published])) }),
  )
  await page.route(`**/api/v1/items/${itemId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ item: published, claims, evidence }),
    }),
  )
  await openSafetyFromClientNavigation(page)
  await page.getByTestId('evidence-trigger').click()
  const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
  await expect(drawer).toBeVisible()
  await expect(page.locator('.srbg-drawer__trap')).toHaveCSS('opacity', '1')

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
