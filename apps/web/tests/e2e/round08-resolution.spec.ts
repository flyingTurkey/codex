import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const candidateId = '019b0000-0000-7000-8000-000000008101'
const sourceItemId = '019b0000-0000-7000-8000-000000008102'
const targetItemId = '019b0000-0000-7000-8000-000000008103'

async function mockHotTopics(page: Page): Promise<void> {
  await page.route('**/api/v1/hot-topics**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      auto_merge_enabled: false,
      evaluation_status: 'INTERNAL_TEST_FIXTURE',
      generated_at: '2026-07-15T03:00:00Z',
      items: [{
        domain: 'SAFETY',
        event_count: 3,
        heat_score: 76,
        id: '019b0000-0000-7000-8000-000000008104',
        independent_source_count: 2,
        latest_activity_at: '2026-07-15T02:00:00Z',
        title: '汛期道路边坡安全动态',
      }],
      window: '7d',
    }),
  }))
}

async function mockRelationWorkbench(page: Page): Promise<{ body: () => unknown }> {
  let decisionBody: unknown
  await page.route('**/api/v1/admin/clustering-workbench**', async (route) => {
    if (route.request().method() === 'POST') {
      decisionBody = route.request().postDataJSON()
      await route.fulfill({ status: 204 })
      return
    }
    const requestedKind = new URL(route.request().url()).searchParams.get('kind')
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(requestedKind === 'RELATION'
        ? [{
            created_at: '2026-07-15T03:00:00Z',
            feature_explanations: ['关系类型：FOLLOW_UP'],
            hard_conflicts: [],
            id: candidateId,
            kind: 'RELATION',
            member_ids: [sourceItemId, targetItemId],
            relation_type: 'FOLLOW_UP',
            score_bps: null,
            status: 'PENDING_REVIEW',
          }]
        : []),
    })
  })
  return { body: () => decisionBody }
}

test('hot topics explain independent sources and keep heat separate from confidence', async ({ page }) => {
  await mockHotTopics(page)
  await page.goto('/hot')

  await expect(page.getByRole('heading', { level: 1, name: '行业热点' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '汛期道路边坡安全动态' })).toBeVisible()
  await expect(page.getByText('独立信源').last()).toBeVisible()
  await expect(page.getByText('内测评估 / 自动合并关闭')).toBeVisible()
  await expect(page.getByText('热点只反映关注变化，不提高事实置信度；同一通稿的转载只计为一个来源链。')).toBeVisible()
  await expect(page.getByText(/置信度\s*\d/)).toHaveCount(0)
})

test('reviewer confirms a follow-up relationship with an audited reason', async ({ page }) => {
  const capture = await mockRelationWorkbench(page)
  await page.goto('/admin/clusters')
  await page.getByLabel('候选类型').selectOption('RELATION')
  await page.getByRole('button', { name: /RELATION/ }).click()
  await page.getByLabel('合并理由 / 拆分理由').fill('官方续报明确承接初报，保留为后续关系')
  await page.getByRole('button', { name: '确认关系' }).click()

  await expect.poll(capture.body).toEqual({
    action: 'LINK_RELATION',
    member_ids: [sourceItemId, targetItemId],
    reason: '官方续报明确承接初报，保留为后续关系',
    relation_type: 'FOLLOW_UP',
  })
})

test('@a11y round 08 hot topics and relation workbench have no axe violations', async ({ page }) => {
  await mockHotTopics(page)
  await page.goto('/hot')
  await expect(page.getByRole('heading', { level: 1, name: '行业热点' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await mockRelationWorkbench(page)
  await page.goto('/admin/clusters')
  await expect(page.getByRole('heading', { level: 1, name: '人工聚类工作台' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
