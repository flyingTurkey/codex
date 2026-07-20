import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

import { v2Feed } from './v2-fixtures'

const eventId = '019f7c00-0000-7000-8000-000000000011'
const claimId = '019f7c00-0000-7000-8000-000000000012'

const fullProjection = {
  projection_kind: 'FULL',
  event_id: eventId,
  title: '隧道瓦斯监测系统投入运营',
  primary_type: 'SAFETY_INTELLIGENCE',
  facets: { engineering_objects: ['TUNNEL'], specialties: ['TUNNEL_GAS_MONITORING'], equipment_domains: [] },
  source: { name: '国家矿山安全监察局', official: true },
  human_reviewed: false,
  source_published_at: '2026-07-18T01:00:00Z',
  first_discovered_at: '2026-07-18T01:05:00Z',
  source_excerpt: { text: '项目在运营隧道部署瓦斯监测与联动预警。', claim_ids: [claimId], evidence_locators: ['p:3'] },
  ai_summary: {
    status: 'SUCCEEDED', status_message: 'AI 总结已生成，并通过结构与证据引用校验。',
    body: '发生了什么：项目部署监测系统。\n工程影响与意义：支持现场预警。\n限制与待跟踪：长期效果仍需跟踪。',
    paragraphs: [
      { kind: 'FACT', section: 'WHAT_HAPPENED', text: '项目部署监测系统。', claim_ids: [claimId], judgment_type: null },
      { kind: 'JUDGMENT', section: 'ENGINEERING_IMPACT', text: '系统有助于支持现场预警。', claim_ids: [], judgment_type: 'ENGINEERING_SIGNIFICANCE' },
      { kind: 'JUDGMENT', section: 'LIMITATIONS_AND_FOLLOW_UP', text: '长期效果仍需持续跟踪。', claim_ids: [], judgment_type: 'LIMITATION_AND_FOLLOW_UP' },
    ],
    claim_ids: [claimId], judgment_paragraphs: [2, 3], model: 'deepseek-chat', generated_at: '2026-07-18T02:00:00Z',
  },
  original_url: 'https://example.com/tunnel-gas',
  claim_basis: ['AUTHORITY_FINDING'],
  hotspot: { trigger: 'MULTI_SOURCE_7D', independent_source_count: 2, reasons: ['两个独立合格来源在七日内报道同一工程事实'] },
  media: [],
  attachments: [{
    media_id: null, name: '项目原站材料', download_url: null,
    source_url: 'https://example.com/material', redistribution_allowed: false,
  }],
  correction_alert: null,
}

async function mockAncillary(page: import('@playwright/test').Page): Promise<void> {
  await page.route('**/api/v1/version', route => route.fulfill({ json: { api_version: 'v2', content_schema_version: '2.0.0' } }))
  await page.route('**/api/v1/sources', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/source-discovery/settings', route => route.fulfill({ json: { automation_enabled: false } }))
}

test('v2 home starts empty and places search above 今日精选', async ({ page }) => {
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({
    json: { items: [], next_cursor: null, generated_at: '2026-07-19T01:00:00Z', projection_generation: 'v2' },
  }))
  await page.goto('/')
  const search = page.getByRole('search', { name: '搜索行业情报' })
  const heading = page.getByRole('heading', { level: 1, name: '今日精选' })
  await expect(search).toBeVisible()
  await expect(heading).toBeVisible()
  expect(await search.evaluate((node, target) => Boolean(node.compareDocumentPosition(target as Node) & Node.DOCUMENT_POSITION_FOLLOWING), await heading.elementHandle())).toBe(true)
  await expect(page.getByText('暂无精选内容')).toBeVisible()
})

test('v2 search announces its loading state precisely', async ({ page }) => {
  await page.route('**/api/v2/search**', async (route) => {
    await new Promise(resolve => setTimeout(resolve, 750))
    await route.fulfill({ json: v2Feed([]) })
  })

  await page.goto('/search?q=%E9%9A%A7%E9%81%93')
  await expect(page.getByRole('status', { name: '正在加载搜索结果' })).toBeVisible()
})

test('@a11y v2 search explains evidence and low-weight AI before opening the unified reader', async ({ page }) => {
  await page.route('**/api/v2/search**', route => route.fulfill({ json: {
    items: [{
      ...fullProjection,
      search_explanation: {
        matched_evidence_fields: ['TITLE', 'SOURCE_EXCERPT'],
        ai_summary_assisted: true,
      },
    }],
    next_cursor: null,
    generated_at: '2026-07-19T01:00:00Z',
    projection_generation: 'v2',
  } }))
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))

  await page.goto('/search?q=%E9%9A%A7%E9%81%93')
  await expect(page.getByText('原文摘录：项目在运营隧道部署瓦斯监测与联动预警。')).toBeVisible()
  await expect(page.getByText(/发生了什么：项目部署监测系统/)).toBeVisible()
  await expect(page.getByText(/证据字段命中：标题、原文摘录/)).toBeVisible()
  await expect(page.getByText('AI 总结低权重辅助召回')).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await page.getByRole('link', { name: fullProjection.title }).click()
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}$`))
  await expect(page.getByRole('heading', { level: 1, name: fullProjection.title })).toBeVisible()
})

test('v2 R3 search card keeps the server metadata whitelist', async ({ page }) => {
  await page.route('**/api/v2/search**', route => route.fulfill({ json: {
    items: [{
      projection_kind: 'R3_METADATA',
      event_id: eventId,
      title: '待审核隧道信息',
      primary_type: 'SAFETY_INTELLIGENCE',
      official_source: true,
      source_name: '国家铁路局',
      source_published_at: null,
      first_discovered_at: null,
      original_url: 'https://example.gov.cn/pending',
      review_state: 'PENDING_OWNER_REVIEW',
    }],
    next_cursor: null,
    generated_at: '2026-07-19T01:00:00Z',
    projection_generation: 'v2',
  } }))

  await page.goto('/search?q=%E9%9A%A7%E9%81%93')
  await expect(page.getByText('待审核隧道信息')).toBeVisible()
  await expect(page.getByText('国家铁路局')).toBeVisible()
  const card = page.locator('article')
  await expect(card.getByText('原文摘录')).toHaveCount(0)
  await expect(card.getByText('AI 总结')).toHaveCount(0)
  await expect(card.getByText('证据字段命中')).toHaveCount(0)
})

test('v2 home keeps search, title, and timeline in DOM and visual order', async ({ page }) => {
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([{
    id: eventId,
    title: '公路隧道监测预警更新',
    source_name: '四川省交通运输厅',
    source_published_at: '2026-07-19T01:00:00Z',
    domain: 'SAFETY',
  }]) }))

  await page.goto('/')
  const search = page.getByRole('search', { name: '搜索行业情报' })
  const heading = page.getByRole('heading', { level: 1, name: '今日精选' })
  const timelineItem = page.getByText('公路隧道监测预警更新', { exact: true })
  const [searchBox, headingBox, itemBox] = await Promise.all([
    search.boundingBox(),
    heading.boundingBox(),
    timelineItem.boundingBox(),
  ])

  expect(searchBox?.y).toBeLessThan(headingBox?.y ?? 0)
  expect(headingBox?.y).toBeLessThan(itemBox?.y ?? 0)
  expect(await search.evaluate((node, target) => Boolean(
    node.compareDocumentPosition(target as Node) & Node.DOCUMENT_POSITION_FOLLOWING,
  ), await timelineItem.elementHandle())).toBe(true)
})

test('v2 feed filters do not duplicate the home search', async ({ page }) => {
  await page.route('**/api/v2/**', route => route.fulfill({ json: v2Feed([]) }))
  for (const path of ['/selected', '/all', '/digital', '/safety', '/industry', '/hot']) {
    await page.goto(path)
    await expect(page.getByRole('search', { name: '搜索行业情报' })).toHaveCount(0)
  }
})

test('v2 search exposes empty and error result states', async ({ page }) => {
  await page.route('**/api/v2/search**', route => route.fulfill({ json: v2Feed([]) }))
  await page.goto('/search?q=%E9%9A%A7%E9%81%93')
  await expect(page.getByText('没有找到匹配情报')).toBeVisible()

  await page.unroute('**/api/v2/search**')
  await page.route('**/api/v2/search**', route => route.fulfill({
    status: 503,
    json: {
      detail: '搜索服务暂时无法响应。',
      request_id: '019f7c00-0000-7000-8000-000000000099',
      status: 503,
      title: '搜索暂不可用',
      type: 'about:blank',
    },
  }))
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('搜索暂不可用')
})

test('v2 home search keeps keyboard order and 200% equivalent reflow', async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 720 })
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([]) }))
  await page.goto('/')

  const searchbox = page.getByRole('searchbox', { name: '搜索行业情报' })
  await expect(page.getByText('搜索行业情报', { exact: true })).toBeVisible()
  await searchbox.focus()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '搜索', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})

test('v2 full reader keeps evidence first and diagnostics folded', async ({ page }) => {
  let appendixRequests = 0
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))
  await page.route(`**/api/v2/events/${eventId}/appendix`, route => route.fulfill({
    json: {
      event_id: eventId, claims: [], evidence: [], automatic_results: [], relationships: [],
      automatic_relationships: [], corrections: [], review_context: null, review_href: '/review',
      content_summary: { total_items: 0, heavy_content: false, truncated_sections: [] },
    },
  }))
  page.on('request', (request) => {
    if (request.url().endsWith(`/api/v2/events/${eventId}/appendix`)) appendixRequests += 1
  })
  await page.goto(`/events/${eventId}`)
  await expect(page.getByRole('heading', { level: 1, name: fullProjection.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toBeVisible()
  await expect(page.getByText('官方一手来源', { exact: true })).toBeVisible()
  await expect(page.getByText('机器整理／未人工复核', { exact: true })).toBeVisible()
  await expect(page.getByText('权威认定', { exact: true })).toBeVisible()
  await expect(page.getByText('两个独立合格来源在七日内报道同一工程事实')).toBeVisible()
  await expect(page.getByText(/总分/)).toHaveCount(0)
  await expect(page.getByRole('link', { name: '查看原文' })).toHaveCount(1)
  await expect(page.getByRole('link', { name: '在原站查看项目原站材料' })).toHaveCount(1)
  await expect(page.getByText(`AcceptedClaim：${claimId}`)).toBeVisible()
  await expect(page.getByText('AI 判断', { exact: true })).toHaveCount(2)
  const appendix = page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })
  await expect(appendix).toHaveAttribute('aria-expanded', 'false')
  expect(appendixRequests).toBe(0)
  await appendix.click()
  await expect(page.getByText('附录当前没有治理记录。')).toBeVisible()
  expect(appendixRequests).toBe(1)
  await appendix.click()
  await appendix.click()
  expect(appendixRequests).toBe(1)
})

test('appendix failure preserves the reader and retries without copying governance forms', async ({ page }) => {
  let attempts = 0
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))
  await page.route(`**/api/v2/events/${eventId}/appendix`, async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { code: 'APPENDIX_UNAVAILABLE', title: 'Unavailable' } })
      return
    }
    await route.fulfill({
      json: {
        event_id: eventId, claims: [], evidence: [], automatic_results: [], relationships: [],
        automatic_relationships: [], corrections: [], review_context: null, review_href: '/review',
        content_summary: { total_items: 0, heavy_content: false, truncated_sections: [] },
      },
    })
  })

  await page.goto(`/events/${eventId}`)
  await page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ }).click()
  await expect(page.getByText('治理附录加载失败。主阅读内容不受影响，请稍后重试。')).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await page.getByRole('button', { name: '重试附录' }).click()
  await expect(page.getByText('附录当前没有治理记录。')).toBeVisible()
  await expect(page.locator('#reader-appendix form')).toHaveCount(0)
})

test('v2 reader uses the B desktop rail and fixed mobile semantic order', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto(`/events/${eventId}`)

  const context = page.locator('[data-reader-area="context"]')
  const excerpt = page.locator('[data-reader-area="source-excerpt"]')
  const summary = page.locator('[data-reader-area="ai-summary"]')
  const actions = page.locator('[data-reader-area="actions"]')
  const desktopAreas = await Promise.all([context, excerpt, summary, actions].map(item => item.evaluate(node => getComputedStyle(node).gridArea)))
  expect(desktopAreas).toEqual(['context', 'excerpt', 'summary', 'actions'])
  expect(await context.evaluate(node => getComputedStyle(node).position)).toBe('sticky')
  expect(await context.evaluate(node => getComputedStyle(node).overflowY)).toBe('visible')

  await page.setViewportSize({ width: 768, height: 1024 })
  const orderedAreas = ['context', 'source-excerpt', 'ai-summary', 'materials', 'actions', 'appendix']
  const topOffsets = await Promise.all(orderedAreas.map(area => page.locator(`[data-reader-area="${area}"]`).evaluate(node => node.getBoundingClientRect().top)))
  expect(topOffsets).toEqual([...topOffsets].sort((left, right) => left - right))
})

test('licensed media failure never hides evidence or falls back to a remote image @a11y', async ({ page }) => {
  const previewPath = `/api/v2/media/019f7c00-0000-7000-8000-000000000031/preview`
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: {
    ...fullProjection,
    media: [
      {
        media_id: '019f7c00-0000-7000-8000-000000000031',
        name: '服务端安全派生图',
        preview_url: previewPath,
        rights_basis: 'SOURCE_AUTHORIZED',
      },
      {
        media_id: '019f7c00-0000-7000-8000-000000000032',
        name: '没有安全预览的图片',
        preview_url: null,
        rights_basis: 'EXPLICIT_LICENSE',
      },
    ],
  } }))
  await page.route(`**${previewPath}`, route => route.abort('failed'))

  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/events/${eventId}`)
    await expect(page.getByRole('heading', { level: 1, name: fullProjection.title })).toBeVisible()
    await expect(page.getByText(fullProjection.source_excerpt.text)).toBeVisible()
    await expect(page.getByRole('link', { name: '查看原文' })).toBeVisible()
    await expect(page.getByRole('img', { name: '服务端安全派生图' })).toHaveCount(1)
    await expect(page.getByRole('img', { name: '没有安全预览的图片' })).toHaveCount(0)
    expect(await page.locator('img').evaluateAll(nodes => nodes.map(node => node.getAttribute('src'))))
      .toEqual([previewPath])
  }

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
})

test('v2 reader has no horizontal overflow at required viewports', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: {
    ...fullProjection,
    title: '超长标题'.repeat(80),
    source: { name: '超长来源机构名称'.repeat(30), official: true },
  } }))

  for (const width of [320, 640, 768, 1024, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/events/${eventId}`)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth), `overflow at ${width}px`).toBeLessThanOrEqual(width)
  }
})

for (const [status, message] of [
  ['NOT_GENERATED', 'AI 总结尚未生成。已通过证据门禁的原文摘录仍可阅读。'],
  ['PROCESSING', 'AI 总结正在处理中。已通过证据门禁的原文摘录仍可阅读。'],
  ['TEMPORARILY_UNAVAILABLE', 'AI 服务暂时不可用。已通过证据门禁的原文摘录仍可阅读，系统将在恢复后按授权重试。'],
  ['SCHEMA_REJECTED', 'AI 输出未通过结构校验，未进入阅读投影。已通过证据门禁的原文摘录仍可阅读。'],
  ['INSUFFICIENT_EVIDENCE', '当前证据不足以生成 AI 总结。原文摘录仍可阅读。'],
  ['SUCCEEDED', 'AI 总结已生成，并通过结构与证据引用校验。'],
  ['STALE', '原文、AcceptedClaims 或更正状态已变化，旧 AI 总结已失效且不会作为当前内容展示。'],
] as const) {
  test(`v2 reader presents ${status} as a distinct summary state`, async ({ page }) => {
    const summary = status === 'SUCCEEDED'
      ? fullProjection.ai_summary
      : { status, status_message: message, body: null, paragraphs: [], claim_ids: [], judgment_paragraphs: [], model: null, generated_at: null }
    await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: {
      ...fullProjection,
      ai_summary: summary,
      correction_alert: status === 'STALE' ? '原文已更正，旧总结已失效。' : null,
    } }))
    await page.goto(`/events/${eventId}`)
    await expect(page.getByText(message, { exact: true })).toBeVisible()
    await expect(page.locator('[data-summary-state]')).toHaveAttribute('data-summary-state', status)
    if (status === 'STALE') await expect(page.getByRole('alert')).toContainText('旧总结已失效')
  })
}

test('v2 R3 reader exposes metadata only and unprojected R4 is not found', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: {
    projection_kind: 'R3_METADATA', event_id: eventId, title: '待审核安全初报', primary_type: 'SAFETY_INTELLIGENCE',
    source_name: '权威机关', official_source: true, source_published_at: null,
    first_discovered_at: '2026-07-19T01:00:00Z', original_url: 'https://example.com/r3', review_state: 'PENDING_OWNER_REVIEW',
  } }))
  await page.goto(`/events/${eventId}`)
  await expect(page.getByText('待 Owner 审核')).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toHaveCount(0)

  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ status: 404, json: { detail: 'Event not found' } }))
  await page.reload()
  await expect(page.getByText(/不可见|无法响应|not found/i)).toBeVisible()
})

test('v2 empty home has no serious accessibility violations @a11y', async ({ page }) => {
  await mockAncillary(page)
  await page.route('**/api/v2/feed**', route => route.fulfill({
    json: { items: [], next_cursor: null, generated_at: '2026-07-19T01:00:00Z', projection_generation: 'v2' },
  }))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
})

test('v2 Owner reader keeps semantic headings and keyboard actions accessible @a11y', async ({ page }) => {
  await page.route(`**/api/v2/events/${eventId}`, route => route.fulfill({ json: fullProjection }))
  await page.setViewportSize({ width: 320, height: 900 })
  await page.goto(`/events/${eventId}`)

  await expect(page.getByRole('heading', { level: 1, name: fullProjection.title })).toBeVisible()
  const original = page.getByRole('link', { name: '查看原文' })
  await original.focus()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: '在原站查看项目原站材料' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: /证据、关系、更正与自动处理附录/ })).toBeFocused()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
})
