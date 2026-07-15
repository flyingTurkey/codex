import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const taskId = '019b0000-0000-7000-8000-000000004700'
const itemId = '019b0000-0000-7000-8000-000000004701'
const deathClaimId = '019b0000-0000-7000-8000-000000004702'
const causeClaimId = '019b0000-0000-7000-8000-000000004703'
const deathEvidenceId = '019b0000-0000-7000-8000-000000004704'
const causeEvidenceId = '019b0000-0000-7000-8000-000000004705'

type DecisionStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED'

function reviewDetail(statuses: Record<string, DecisionStatus>) {
  return {
    claims: [
      {
        claim_type: 'deaths',
        decision_status: statuses[deathClaimId],
        evidence_ids: [deathEvidenceId],
        id: deathClaimId,
        label: '死亡人数',
        value: '52 人',
      },
      {
        claim_type: 'official_direct_causes',
        decision_status: statuses[causeClaimId],
        evidence_ids: [causeEvidenceId],
        id: causeClaimId,
        label: '正式调查直接原因',
        value: '长时间持续性降水与多种因素叠加耦合作用',
      },
    ],
    evidence: [
      {
        claim_ids: [deathClaimId],
        excerpt: '事故共造成 52 人死亡、30 人受伤。',
        excerpt_sha256: 'a'.repeat(64),
        id: deathEvidenceId,
        original_url: 'https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/content/post_4658975.html',
        paragraph_id: 'investigation-p-0042',
      },
      {
        claim_ids: [causeClaimId],
        excerpt: '调查报告认定，长时间持续性降水与多种因素叠加耦合作用。',
        excerpt_sha256: 'b'.repeat(64),
        id: causeEvidenceId,
        original_url: 'https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/content/post_4658975.html',
        paragraph_id: 'investigation-p-0108',
      },
    ],
    item: {
      activity_at: '2025-01-22T04:00:00Z',
      content_type: 'SAFETY_CASE',
      domain: 'SAFETY',
      evidence_count: 2,
      evidence_status: 'VERIFIED',
      first_discovered_at: '2025-01-22T04:05:00Z',
      id: itemId,
      original_url: 'https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/content/post_4658975.html',
      publication_revision_id: null,
      publication_status: 'PENDING_REVIEW',
      review_status: 'PENDING',
      source_name: '广东省应急管理厅',
      source_published_at: '2025-01-22T04:00:00Z',
      title: '梅大高速茶阳路段“5·1”塌方灾害调查报告',
      type_summary: {
        incident_status: 'FINAL_INVESTIGATION_REPORT',
        kind: 'SAFETY_CASE',
        report_stage: 'FINAL_INVESTIGATION',
      },
    },
    task: {
      id: taskId,
      item_id: itemId,
      risk_level: 'R3',
      source_name: '广东省应急管理厅',
      status: 'PENDING',
      submitted_at: '2025-01-22T04:05:00Z',
      submitted_by: '019b0000-0000-7000-8000-000000004799',
      title: '梅大高速茶阳路段“5·1”塌方灾害调查报告',
    },
  }
}

async function mockReview(page: Page): Promise<{ decisions: () => unknown[] }> {
  const statuses: Record<string, DecisionStatus> = {
    [deathClaimId]: 'PENDING',
    [causeClaimId]: 'PENDING',
  }
  const decisions: unknown[] = []

  await page.route(`**/api/v1/admin/review-tasks/${taskId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(reviewDetail(statuses)),
    }),
  )
  await page.route('**/api/v1/admin/review-candidates/CLAIM/*/decisions', async (route) => {
    const claimId = route.request().url().split('/').at(-2)
    const body = route.request().postDataJSON() as { action: 'ACCEPT' | 'REJECT' }
    decisions.push({ claimId, body })
    if (claimId) statuses[claimId] = body.action === 'ACCEPT' ? 'ACCEPTED' : 'REJECTED'
    await route.fulfill({ contentType: 'application/json', body: '{}' })
  })
  return { decisions: () => decisions }
}

async function openReview(page: Page): Promise<void> {
  await page.goto(`/admin/review/${taskId}`)
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
  await expect(page.getByRole('heading', { level: 1, name: 'R3 审核详情' })).toBeVisible()
}

test('safety case critical claims require evidence-linked field decisions before publish', async ({ page }) => {
  const capture = await mockReview(page)
  await openReview(page)

  const publish = page.getByRole('button', { name: '批准并发布' })
  await expect(publish).toBeDisabled()
  await expect(page.getByText('所有关键字段完成接受或拒绝后，才能批准并发布。')).toBeVisible()
  const casualtyEvidence = page.getByText('事故共造成 52 人死亡、30 人受伤。')
  const causeEvidence = page.getByText('调查报告认定，长时间持续性降水与多种因素叠加耦合作用。')
  await expect(casualtyEvidence).toHaveCount(2)
  await expect(casualtyEvidence.first()).toBeVisible()
  await expect(casualtyEvidence.last()).toBeVisible()
  await expect(causeEvidence).toHaveCount(2)
  await expect(causeEvidence.first()).toBeVisible()
  await expect(causeEvidence.last()).toBeVisible()

  await page.getByLabel('死亡人数审核说明').fill('正式调查报告逐字段核对无误')
  await page.getByRole('button', { name: '接受死亡人数' }).click()
  await expect(page.getByText('已接受', { exact: true })).toBeVisible()
  await expect(publish).toBeDisabled()

  await page.getByLabel('正式调查直接原因审核说明').fill('仅采用有权机关正式调查结论')
  await page.getByRole('button', { name: '拒绝正式调查直接原因' }).click()
  await expect(page.getByText('已拒绝', { exact: true })).toBeVisible()
  await expect(publish).toBeEnabled()

  expect(capture.decisions()).toEqual([
    {
      claimId: deathClaimId,
      body: {
        action: 'ACCEPT',
        reason: '正式调查报告逐字段核对无误',
        target_document_id: null,
      },
    },
    {
      claimId: causeClaimId,
      body: {
        action: 'REJECT',
        reason: '仅采用有权机关正式调查结论',
        target_document_id: null,
      },
    },
  ])
})

test('@a11y pending safety case field review has no axe violations', async ({ page }) => {
  await mockReview(page)
  await openReview(page)

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
