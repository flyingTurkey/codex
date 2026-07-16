import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const eventId = '019b0000-0000-7000-8000-000000004001'
const investigationItemId = '019b0000-0000-7000-8000-000000004002'
const followUpItemId = '019b0000-0000-7000-8000-000000004004'

const safetyCase = {
  activity_at: '2024-05-02T12:03:56Z',
  content_type: 'SAFETY_CASE',
  domain: 'SAFETY',
  evidence_count: 2,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2025-01-22T04:05:00Z',
  id: followUpItemId,
  original_url: 'https://www.dabu.gov.cn/hygq/xwfbh/content/mpost_2628990.html',
  publication_revision_id: '019b0000-0000-7000-8000-000000004003',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '大埔县人民政府门户',
  source_published_at: '2024-05-02T12:03:56Z',
  source_role: '官方一手来源',
  title: '梅州举行梅大高速茶阳路段塌方救援新闻发布会',
  type_summary: {
    conflicted_fields: ['DEATH_COUNT'],
    engineering_type: 'EXPRESSWAY',
    event_id: eventId,
    hazard_type: 'ROADBED_COLLAPSE',
    incident_status: 'UNDER_INVESTIGATION',
    kind: 'SAFETY_CASE',
    occurred_at: null,
    region: '广东省',
    report_stage: 'FOLLOW_UP_REPORT',
  },
}

const investigationItem = {
  ...safetyCase,
  activity_at: '2025-01-22T09:00:00Z',
  id: investigationItemId,
  original_url: 'https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/content/post_4658975.html',
  source_name: '广东省应急管理厅',
  source_published_at: '2025-01-22T09:00:00Z',
  title: '梅大高速茶阳路段“5·1”塌方灾害调查报告',
  type_summary: {
    ...safetyCase.type_summary,
    conflicted_fields: [],
    incident_status: 'FINAL_INVESTIGATION_REPORT',
    occurred_at: '2024-04-30T17:57:00Z',
    report_stage: 'FINAL_INVESTIGATION',
  },
}

const timeline = [
  ['INITIAL_REPORT', 'INITIAL_OFFICIAL_REPORT', null, '事故初报：24人死亡、30人受伤', 'https://www.dabu.gov.cn/zwgk/wxgk/jggk/lsqkgk/content/mpost_2630342.html', '大埔县人民政府门户', '2024-05-01T12:10:42Z'],
  ['FOLLOW_UP_REPORT', 'UNDER_INVESTIGATION', 'FOLLOW_UP', '救援续报：伤亡数字更新', safetyCase.original_url, '大埔县人民政府门户', '2024-05-02T12:03:56Z'],
  ['FINAL_INVESTIGATION', 'FINAL_INVESTIGATION_REPORT', 'INVESTIGATES', '正式调查报告公布', investigationItem.original_url, '广东省应急管理厅', '2025-01-22T09:00:00Z'],
  ['ENFORCEMENT', 'ENFORCEMENT_DECISION', 'PENALIZES', '追责问责情况通报', 'https://www.gdjct.gd.gov.cn/zhyw/content/post_204625.html', '中共广东省纪委、广东省监察委员会', '2025-01-25T04:00:00Z'],
  ['RECTIFICATION', 'RECTIFICATION_FOLLOW_UP', 'RECTIFIES', '整改措施落实评估报告', 'https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/content/post_4873850.html', '广东省应急管理厅', '2026-03-24T06:32:00Z'],
].map(([report_stage, incident_status, relation_type, title, original_url, source_name, publishedAt], index) => ({
  document_states: [],
  evidence_count: index + 1,
  incident_status,
  item_id: index === 2 ? investigationItemId : `019b0000-0000-7000-8000-00000000410${index}`,
  original_url,
  publication_revision_id: `019b0000-0000-7000-8000-00000000420${index}`,
  relation_type,
  report_stage,
  review_status: 'APPROVED',
  source_name,
  source_published_at: publishedAt,
  title,
}))

const relationReviewerId = '019b0000-0000-7000-8000-000000004799'
const eventRelations = [
  ['FOLLOW_UP', '019b0000-0000-7000-8000-000000004101', '019b0000-0000-7000-8000-000000004100', '2024-05-02T06:00:00Z'],
  ['INVESTIGATES', investigationItemId, '019b0000-0000-7000-8000-000000004101', '2025-01-22T08:00:00Z'],
  ['PENALIZES', '019b0000-0000-7000-8000-000000004103', investigationItemId, '2025-01-25T08:00:00Z'],
  ['RECTIFIES', '019b0000-0000-7000-8000-000000004104', '019b0000-0000-7000-8000-000000004103', '2026-03-24T08:00:00Z'],
  ['CORRECTS', investigationItemId, '019b0000-0000-7000-8000-000000004101', '2025-01-22T09:00:00Z'],
].map(([relation_type, from_item_id, to_item_id, reviewed_at], index) => ({
  event_id: eventId,
  from_item_id,
  id: `019b0000-0000-7000-8000-00000000450${index}`,
  relation_type,
  reviewed_at,
  reviewed_by: relationReviewerId,
  to_item_id,
}))

const eventDetail = {
  claims: [{
    claim_id: '019b0000-0000-7000-8000-000000004010',
    evidence_ids: ['019b0000-0000-7000-8000-000000004011'],
    field_name: 'OFFICIAL_DIRECT_CAUSES',
    value: '长时间持续性降水与多种因素叠加耦合作用',
  }],
  confirmed_facts: [
    {
      claim_id: '019b0000-0000-7000-8000-000000004010',
      evidence_ids: ['019b0000-0000-7000-8000-000000004011'],
      field: 'OFFICIAL_DIRECT_CAUSES',
      label: '正式调查认定的直接原因',
      source_item_id: investigationItemId,
      status: 'CONFIRMED',
      unit: null,
      value: ['长时间持续性降水与多种因素叠加耦合作用'],
      reviewed_at: '2025-01-22T08:00:00Z',
    },
  ],
  engineering_type: 'EXPRESSWAY',
  evidence: [{
    content_sha256: 'a'.repeat(64),
    evidence_id: '019b0000-0000-7000-8000-000000004011',
    locator: 'html-p-0042',
  }],
  hazard_type: 'ROADBED_COLLAPSE',
  id: eventId,
  incident_status: 'RECTIFICATION_FOLLOW_UP',
  occurred_at: '2024-04-30T17:57:00Z',
  prevention_measure_tags: ['MONITORING_AND_EARLY_WARNING', 'INSPECTION_AND_MAINTENANCE'],
  project_name: '梅大高速',
  rectification_has_open_issues: true,
  region: '广东省',
  relations: eventRelations,
  similar_scenario_tags: ['HIGHWAY_OPERATION_GEOLOGICAL_RISK', 'ROADBED_SLOPE_INSTABILITY'],
  timeline: { event_id: eventId, items: timeline },
  title: '梅大高速茶阳路段“5·1”塌方灾害',
  unverified_facts: [
    {
      claim_id: null,
      conflict_id: '019b0000-0000-7000-8000-000000004013',
      display_value: '待核实',
      evidence_ids: [],
      field: 'DEATH_COUNT',
      label: '阶段性伤亡数字',
      reason: '初报、续报与正式调查报告数字不同，保留各阶段并进入人工核实。',
      source_item_id: investigationItemId,
      status: 'CONFLICTING',
      value: null,
    },
  ],
}

function feed(items: unknown[]) {
  return {
    fingerprint: 'sha256:round04-e2e',
    freshness: 'fresh',
    generated_at: '2026-07-14T01:09:04Z',
    items,
    next_cursor: null,
    notices: [],
  }
}

async function mockSafetyCasePath(page: Page): Promise<void> {
  await page.route('**/api/v1/feed**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(feed([safetyCase])) }),
  )
  await page.route(`**/api/v1/events/${eventId}`, (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(eventDetail) }),
  )
}

test('/all keeps its content-type filter usable without a parent v-model binding', async ({ page }) => {
  const regulation = {
    ...safetyCase,
    content_type: 'SAFETY_REGULATION',
    id: '019b0000-0000-7000-8000-000000004099',
    title: '生产安全事故报告和调查处理规定',
    type_summary: null,
  }
  await page.route('**/api/v1/feed**', (route) => {
    const selectedType = new URL(route.request().url()).searchParams.get('content_type')
    const items = selectedType === 'SAFETY_REGULATION'
      ? [regulation]
      : [regulation, safetyCase]
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(feed(items)),
    })
  })

  await page.goto('/all')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })
  await expect(page.getByRole('heading', { name: regulation.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: safetyCase.title })).toBeVisible()

  const regulationFilter = page.locator('[data-content-type="SAFETY_REGULATION"]')
  await regulationFilter.click()

  await expect(regulationFilter).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: regulation.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: safetyCase.title })).toBeHidden()
})

test('safety case filter is server-backed and the five-stage event remains evidence-linked', async ({ page }) => {
  await mockSafetyCasePath(page)
  await page.goto('/safety')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 15_000,
  })

  const caseRequest = page.waitForRequest((request) =>
    new URL(request.url()).searchParams.get('content_type') === 'SAFETY_CASE',
  )
  await page.getByRole('button', { name: '案例', exact: true }).click()
  await caseRequest

  await expect(page.getByText('安全案例', { exact: true })).toBeVisible()
  await expect(page.getByTestId('case-status')).toContainText('调查中')
  await expect(page.getByTestId('case-conflict')).toContainText('冲突待核实')
  await page.getByTestId('event-link').click()

  await expect(page).toHaveURL(new RegExp(`/events/${eventId}$`))
  await expect(page.getByRole('heading', { level: 1, name: eventDetail.title })).toBeVisible()
  await expect(page.getByText('整改评估完成但仍有问题', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '已确认事实' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '待核实' })).toBeVisible()
  await expect(page.getByText('高速公路', { exact: true })).toBeVisible()
  await expect(page.getByText('路基塌陷', { exact: true })).toBeVisible()
  await expect(page.getByText(/EXPRESSWAY|ROADBED_COLLAPSE/)).toHaveCount(0)
  await expect(page.getByTestId('event-stage')).toHaveCount(5)
  const relations = page.getByTestId('event-relations')
  await expect(relations.getByTestId('event-relation')).toHaveCount(5)
  const correction = relations.locator('[data-relation-type="CORRECTS"]')
  await expect(correction.getByText('更正前序材料', { exact: true })).toBeVisible()
  await expect(correction.getByText('正式调查报告公布', { exact: true })).toBeVisible()
  await expect(correction.getByText('救援续报：伤亡数字更新', { exact: true })).toBeVisible()
  await expect(correction.getByText('2025年1月22日 17:00', { exact: true })).toBeVisible()
  await expect(relations).not.toContainText(relationReviewerId)
  await expect(relations).not.toContainText('019b0000-0000-7000-8000-00000000450')
  await expect(relations).not.toContainText('长时间持续性降水与多种因素叠加耦合作用')
  await expect(
    page.getByLabel('事件时间线').getByText('正式调查报告公布', { exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('[data-fact-state="unverified"]').getByText('冲突待核实', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('[data-fact-state="unverified"]')).not.toContainText(/\d+\s*人/)
  await expect(page.getByText(/019b0000-0000-7000-8000-00000000401[0-3]/)).toHaveCount(0)
  await expect(page.getByText('运营高速公路地质风险', { exact: true })).toBeVisible()
  await expect(page.getByText('现场操作指令', { exact: false })).toHaveCount(0)

  await page.getByTestId('fact-evidence-trigger').click()
  const drawer = page.getByRole('dialog', { name: '原文段落与页码定位' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByText('html-p-0042', { exact: false })).toBeVisible()
  await expect(drawer.getByText('a'.repeat(64), { exact: true })).toBeVisible()
  await expect(drawer).not.toContainText(investigationItem.original_url)
})

test('@a11y safety case event path has no axe violations at 768px', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await mockSafetyCasePath(page)
  await page.goto(`/events/${eventId}`)
  await expect(page.getByTestId('event-stage')).toHaveCount(5)
  await page.getByTestId('fact-evidence-trigger').click()
  await expect(page.getByRole('dialog', { name: '原文段落与页码定位' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
