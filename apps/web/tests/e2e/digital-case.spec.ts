import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const itemId = '019b0000-0000-7000-8000-000000005201'
const taskId = '019b0000-0000-7000-8000-000000005202'
const entityId = '019b0000-0000-7000-8000-000000005203'
const claimId = '019b0000-0000-7000-8000-000000005204'
const evidenceId = '019b0000-0000-7000-8000-000000005205'
const outcomeId = '019b0000-0000-7000-8000-000000005206'

const item = {
  activity_at: '2026-07-14T04:00:00Z',
  content_type: 'DIGITAL_CASE',
  domain: 'DIGITAL',
  evidence_count: 1,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-14T04:05:00Z',
  id: itemId,
  original_url: 'https://www.shudaojt.com/public/uploads/files/2022/03/example.pdf',
  publication_revision_id: '019b0000-0000-7000-8000-000000005207',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  scores: {
    authority: null,
    confidence: null,
    evidence: null,
    heat: null,
    impact: null,
    novelty: null,
    relevance: {
      calculated_at: '2026-07-14T04:10:00Z',
      dimension: 'RELEVANCE',
      features: [
        { code: 'ENGINEERING_DOMAIN', explanation: '桥梁工程领域匹配', label: '工程专业匹配', points: 70 },
        { code: 'SICHUAN', explanation: '案例在四川实施', label: '四川实施', points: 20 },
        { code: 'SRBG_DIRECT', explanation: '四川路桥所属单位实施', label: '直接关系', points: 10 },
      ],
      overridden: false,
      raw_score: 100,
      rule_version: 'relevance-v1.0.0',
      score: 100,
    },
    timeliness: null,
  },
  source_name: '蜀道集团',
  source_published_at: '2022-03-10T00:00:00Z',
  source_role: '企业自述',
  title: '智慧梁厂 2.0',
  type_summary: {
    application_scenarios: ['QUALITY_CONTROL'],
    deployment_scale: '沿江高速项目梁场',
    kind: 'DIGITAL_CASE',
    maturity_level: 'PILOT',
    publisher_claim_label: '厂商声明，未经独立验证',
    relevance: {
      factors: [
        { code: 'ENGINEERING_DOMAIN', label: '工程专业匹配', points: 70 },
        { code: 'SICHUAN', label: '四川实施', points: 20 },
        { code: 'SRBG_DIRECT', label: '四川路桥直接关系', points: 10 },
      ],
      rule_version: 'relevance-v1.0.0',
      score: 100,
    },
    source_nature: 'ENTERPRISE_SELF_REPORT',
    srbg_relationship: '四川路桥所属单位实施项目',
  },
}

const digitalCase = {
  application_scenarios: ['QUALITY_CONTROL'],
  applicability: ['桥梁预制梁生产过程'],
  claimed_outcomes: [{
    attribution: '蜀道集团',
    evidence_ids: [evidenceId],
    id: outcomeId,
    independent_evidence_ids: [],
    statement: '发布方称可提高梁片生产协同效率',
    verification: 'CLAIMED',
  }],
  deployment_scale: '沿江高速项目梁场',
  engineering_domains: ['BRIDGE'],
  entities: [{
    claim_id: claimId,
    entity_type: 'ORGANIZATION',
    id: entityId,
    name: '蜀道集团',
    relation_type: 'PUBLISHER',
  }],
  lifecycle_stages: ['CONSTRUCTION'],
  limitations: ['缺少独立运行效果验证'],
  maturity_level: 'PILOT',
  recommended_actions: ['READ_ORIGINAL', 'SAVE', 'FOLLOW', 'TECHNICAL_RESEARCH'],
  replication_conditions: ['需结合梁场工艺和数据接口调研'],
  risks: ['厂商自述可能存在选择性披露'],
  technology_tags: ['BIM'],
  verified_outcomes: [],
}

const claims = [{
  claim_type: 'outcome',
  evidence_ids: [evidenceId],
  id: claimId,
  label: '发布方成效声明',
  value: '提高梁片生产协同效率',
}]
const evidence = [{
  claim_ids: [claimId],
  excerpt: '本案例由企业发布材料整理，相关成效为发布方声明。',
  excerpt_sha256: 'a'.repeat(64),
  id: evidenceId,
  original_url: item.original_url,
  page_number: 64,
  paragraph_id: 'pdf-page-64',
}]

function feed() {
  return {
    fingerprint: 'sha256:round05-e2e',
    freshness: 'fresh',
    generated_at: '2026-07-14T04:10:00Z',
    items: [item],
    next_cursor: null,
    notices: [],
  }
}

async function mockDigital(page: Page): Promise<void> {
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed()) }),
  )
  await page.route(`**/api/v1/items/${itemId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ item, claims, evidence, digital_case: digitalCase }),
    }),
  )
  await page.route(`**/api/v1/events/${itemId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: itemId,
        title: item.title,
        event_type: 'DIGITAL_PROJECT',
        event_status: 'ACTIVE',
        canonical_event_id: itemId,
        event_version: 1,
        confirmed_facts: [],
        unverified_facts: [],
        timeline: { items: [] },
        relations: [],
        similar_scenario_tags: [],
        prevention_measure_tags: [],
        topic_ids: [],
        independent_source_count: 1,
        claims: [{
          claim_id: claimId,
          evidence_ids: [evidenceId],
          field_name: 'CLAIMED_OUTCOME',
          value: '发布方称可提高梁片生产协同效率',
        }],
        evidence: [{
          content_sha256: 'a'.repeat(64),
          evidence_id: evidenceId,
          locator: 'pdf-page-64',
        }],
        type_detail: item.type_summary,
      }),
    }),
  )
}

async function openDigital(page: Page): Promise<void> {
  await page.goto('/digital')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
}

test('digital feed filters shared cards and explains relevance without confidence wording', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await mockDigital(page)
  await openDigital(page)

  await expect(page.getByRole('heading', { level: 1, name: '数字化案例' })).toBeVisible()
  await expect(page.getByText('厂商声明，未经独立验证')).toBeVisible()
  expect(pageErrors).toEqual([])
  await page.getByTestId('score-summary').click()
  await expect(page.getByText('relevance-v1.0.0')).toBeVisible()
  await expect(page.getByText('可信度')).toHaveCount(0)
  await page.getByLabel('工程专业').selectOption('BRIDGE')
  await expect.poll(() => page.url()).not.toContain('undefined')
})

test('digital detail keeps accepted publisher claims linked to Event evidence', async ({ page }) => {
  await mockDigital(page)
  await page.goto(`/events/${itemId}`)

  await expect(page.getByRole('heading', { level: 1, name: item.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '发布方声称的成效' })).toBeVisible()
  await expect(page.getByText('厂商声明，未经独立验证', { exact: true })).toBeVisible()
  await expect(page.getByText('发布方称可提高梁片生产协同效率', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看成效证据（1）' }).click()
  const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
  await expect(drawer).toContainText('pdf-page-64')
  await expect(drawer).toContainText('a'.repeat(64))
  await expect(drawer).toContainText('发布方称可提高梁片生产协同效率')
  await expect(page.getByText('暂无可独立验证的量化成效。')).toBeVisible()
  await expect(page.getByText('来源属性和成熟度摘要不替代具体事实证据。')).toBeVisible()
})

test('reviewer submits digital classifications, maturity, and attribution through one decision', async ({ page }) => {
  await page.goto('/admin/review/019b0000-0000-7000-8000-000000000001')
  await expect(page).toHaveURL(/\/sources\?migrated=legacy-source-management/)
  return
  const decisions: unknown[] = []
  await page.route(`**/api/v1/admin/review-tasks/${taskId}`, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        claims,
        evidence,
        digital_case: digitalCase,
        item: { ...item, publication_revision_id: null, publication_status: 'PENDING_REVIEW', review_status: 'PENDING' },
        task: {
          id: taskId,
          item_id: itemId,
          risk_level: 'R2',
          source_name: '蜀道集团',
          status: 'PENDING',
          submitted_at: '2026-07-14T04:05:00Z',
          submitted_by: '019b0000-0000-7000-8000-000000005299',
          title: item.title,
        },
      }),
    }),
  )
  await page.route(`**/api/v1/admin/review-tasks/${taskId}/decisions`, async (route) => {
    decisions.push(route.request().postDataJSON())
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ review_task_id: taskId, status: 'APPROVED', publication_revision_id: item.publication_revision_id }),
    })
  })

  await page.goto(`/admin/review/${taskId}`)
  await expect(page.getByRole('heading', { name: '数字化案例结构审核' })).toBeVisible()
  await page.getByRole('button', { name: '批准并发布' }).click()

  await expect.poll(() => decisions.length).toBe(1)
  expect(decisions[0]).toMatchObject({
    action: 'APPROVE',
    digital_case_patch: {
      engineering_domains: ['BRIDGE'],
      maturity_level: 'PILOT',
      outcome_attributions: [{ attribution_entity_id: entityId, verification: 'CLAIMED' }],
    },
  })
})

test('@a11y digital feed and detail have no axe violations', async ({ page }) => {
  await mockDigital(page)
  await openDigital(page)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await page.goto(`/events/${itemId}`)
  await expect(page.getByRole('heading', { level: 1, name: item.title })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
