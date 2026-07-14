import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const conflictId = '019b0000-0000-7000-8000-000000004500'
const conflict = {
  candidate_claim_id: '019b0000-0000-7000-8000-000000004502',
  candidate_value: 52,
  current_claim_id: '019b0000-0000-7000-8000-000000004501',
  current_value: 48,
  detected_at: '2025-01-22T08:00:00Z',
  event_id: '019b0000-0000-7000-8000-000000004001',
  field: 'DEATH_COUNT',
  id: conflictId,
  resolution_reason: null,
  resolved_at: null,
  resolved_by: null,
  resolved_claim_id: null,
  status: 'PENDING_REVIEW',
}

async function mockConflictWorkbench(page: Page): Promise<{ decisionBody: () => unknown }> {
  let capturedBody: unknown
  await page.route('**/api/v1/admin/review-tasks', (route) =>
    route.fulfill({ contentType: 'application/json', body: '[]' }),
  )
  await page.route('**/api/v1/admin/claim-conflicts**', async (route) => {
    if (route.request().method() === 'POST') {
      capturedBody = route.request().postDataJSON()
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          action: 'ACCEPT_CANDIDATE',
          conflict_id: conflictId,
          resolved_at: '2025-01-22T09:00:00Z',
          resolved_claim_id: conflict.candidate_claim_id,
          status: 'RESOLVED',
        }),
      })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([conflict]) })
  })
  return { decisionBody: () => capturedBody }
}

async function openConflictWorkbench(page: Page): Promise<void> {
  await page.goto('/admin/review')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
  await expect(page.getByRole('heading', { level: 1, name: '审核工作台' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '关键字段冲突' })).toBeVisible()
}

test('reviewer resolves a casualty conflict with a mandatory audited reason', async ({ page }) => {
  const capture = await mockConflictWorkbench(page)
  await openConflictWorkbench(page)

  const acceptCandidate = page.getByRole('button', { name: '采用候选事实' })
  await expect(acceptCandidate).toBeDisabled()
  await page.getByLabel('死亡人数冲突的处理理由').fill('正式调查报告是更新且经逐字段审核的官方证据')
  await acceptCandidate.click()

  await expect(page.getByText('冲突决定已记录，列表已刷新。', { exact: true })).toBeVisible()
  expect(capture.decisionBody()).toEqual({
    action: 'ACCEPT_CANDIDATE',
    reason: '正式调查报告是更新且经逐字段审核的官方证据',
  })
})

test('@a11y reviewer conflict workbench has no axe violations', async ({ page }) => {
  await mockConflictWorkbench(page)
  await openConflictWorkbench(page)

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
