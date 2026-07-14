import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const itemId = '019b0000-0000-7000-8000-000000003001'
const versionV1 = '019b0000-0000-7000-8000-000000003002'
const versionV3 = '019b0000-0000-7000-8000-000000003003'
const evidenceId = '019b0000-0000-7000-8000-000000003004'
const claimId = '019b0000-0000-7000-8000-000000003005'
const preview = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
)

const item = {
  activity_at: '2026-07-14T03:00:00Z',
  content_type: 'SAFETY_REGULATION',
  document_states: ['UPDATED'],
  domain: 'SAFETY',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-01T00:00:00Z',
  has_version_history: true,
  id: itemId,
  original_url: 'https://www.mem.gov.cn/test-only/round03.pdf',
  publication_revision_id: '019b0000-0000-7000-8000-000000003006',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '应急管理部',
  source_published_at: '2026-07-01T00:00:00Z',
  source_role: '官方一手来源',
  title: '测试专用桥梁施工安全规定',
  type_summary: {
    classification: 'DEPARTMENT_RULE',
    document_number: 'TEST-ONLY-2026-04',
    issuing_authority: '应急管理部',
    kind: 'SAFETY_REGULATION',
    regulation_status: 'UNKNOWN',
  },
}

async function mockRound03(page: Page, withdrawn = false): Promise<void> {
  const projected = withdrawn
    ? { ...item, document_states: ['WITHDRAWN'], publication_revision_id: null, publication_status: 'WITHDRAWN' }
    : item
  await page.route('**/api/v1/feed**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      fingerprint: 'sha256:round03-visual', freshness: 'fresh', generated_at: '2026-07-14T03:00:00Z',
      items: [projected], next_cursor: null, notices: [],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      item,
      claims: [{ claim_type: 'document_number', evidence_ids: [evidenceId], id: claimId, label: '文号', value: 'TEST-ONLY-2026-04' }],
      evidence: [{
        claim_ids: [claimId], document_version_id: versionV3, excerpt: 'Document number: TEST-ONLY-2026-04',
        excerpt_sha256: 'a'.repeat(64), id: evidenceId,
        locator: { bbox: { x0: 72000, x1: 350000, y0: 170000, y1: 205000 }, block_id: claimId, page_number: 2, type: 'PDF_TEXT' },
        original_url: item.original_url,
      }],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}/versions`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      item_id: itemId,
      versions: [
        { acquired_at: '2026-07-01T00:00:00Z', change_type: 'INITIAL', is_current: false, material: true, processing_state: 'READY', review_state: 'APPROVED', version_id: versionV1, version_number: 1 },
        { acquired_at: '2026-07-14T00:00:00Z', change_type: 'CONTENT_UPDATE', is_current: true, material: true, processing_state: 'READY', review_state: 'APPROVED', version_id: versionV3, version_number: 3 },
      ],
    }),
  }))
  await page.route(`**/api/v1/items/${itemId}/diff**`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      changed_token_count: 14, changed_token_ratio_bps: 80, change_type: 'CONTENT_UPDATE',
      critical_fields: [{ after: 'TEST-ONLY-2026-04', before: 'TEST-ONLY-2026-03', field: 'document_number' }],
      from_version_id: versionV1, item_id: itemId, material: true,
      pages: [{ category: 'BODY', hunks: [{ after: 'must inspect before every shift', before: 'shall inspect before use', operation: 'REPLACE' }], page_number: 2 }],
      to_version_id: versionV3,
    }),
  }))
  await page.route(`**/api/v1/document-versions/${versionV3}/pages/*/preview`, route => route.fulfill({
    contentType: 'image/png', body: preview,
  }))
  await page.route(`**/api/v1/document-versions/${versionV3}/pages/*`, route => {
    if (route.request().url().endsWith('/preview')) return route.fallback()
    const pageNumber = Number(route.request().url().split('/').at(-1))
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        document_version_id: versionV3, height_mpt: 842000, page_count: 3, page_number: pageNumber,
        preview_url: `/api/v1/document-versions/${versionV3}/pages/${pageNumber}/preview`,
        rotation: 0, text_source: 'NATIVE', width_mpt: 595000,
      }),
    })
  })
}

async function openSafety(page: Page): Promise<void> {
  await page.goto('/safety')
  await expect(page.locator('.srbg-app-shell[aria-busy="false"]')).toBeVisible({ timeout: 20_000 })
}

const scenarios = [
  { acceptance: 'round-03-pdf-highlight-1920x1080.png', kind: 'highlight', width: 1920, height: 1080 },
  { acceptance: 'round-03-version-diff-1440x900.png', kind: 'diff', width: 1440, height: 900 },
  { acceptance: 'round-03-withdrawn-1024x768.png', kind: 'withdrawn', width: 1024, height: 768 },
  { acceptance: 'round-03-mobile-drawer-768x1024.png', kind: 'highlight', width: 768, height: 1024 },
] as const

for (const scenario of scenarios) {
  test(`round03 ${scenario.kind} visual at ${scenario.width}x${scenario.height}`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: scenario.height })
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
    await mockRound03(page, scenario.kind === 'withdrawn')
    await openSafety(page)
    if (scenario.kind !== 'withdrawn') {
      await page.getByTestId('evidence-trigger').click()
      const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
      await expect(drawer).toBeVisible()
      await expect(drawer.getByTestId('pdf-highlight')).toBeVisible()
      if (scenario.kind === 'diff') await drawer.getByText('版本差异').scrollIntoViewIfNeeded()
    } else {
      await expect(page.getByText('已撤回', { exact: true })).toBeVisible()
      await expect(page.getByTestId('evidence-trigger')).toHaveCount(0)
    }
    const baseline = `round03-${scenario.kind}-${scenario.width}x${scenario.height}.png`
    await expect(page).toHaveScreenshot(baseline, { animations: 'disabled' })
    await page.screenshot({
      animations: 'disabled',
      path: resolve(process.cwd(), '../../docs/acceptance/assets', scenario.acceptance),
    })
  })
}
