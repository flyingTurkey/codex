import type { Page } from '@playwright/test'

const acceptedClaimId = '019f7c00-0000-7000-8000-000000009901'

type LegacyReaderItem = {
  id: string
  title: string
  source_name?: string
  source_published_at?: string | null
  first_discovered_at?: string
  original_url?: string
  domain?: string
  content_type?: string
  one_sentence_fact?: string | null
}

export function v2Projection(item: LegacyReaderItem, options: {
  risk?: 'FULL' | 'R3_METADATA'
  official?: boolean
} = {}) {
  const common = {
    event_id: item.id,
    title: item.title,
    primary_type: item.domain === 'SAFETY' || item.content_type?.startsWith('SAFETY_')
      ? 'SAFETY_INTELLIGENCE'
      : 'DIGITAL_TRANSFORMATION',
    source_published_at: item.source_published_at ?? null,
    first_discovered_at: item.first_discovered_at ?? '2026-07-19T01:00:00Z',
    original_url: item.original_url ?? 'https://example.com/source',
  }
  if (options.risk === 'R3_METADATA') {
    return {
      ...common,
      projection_kind: 'R3_METADATA',
      official_source: options.official ?? true,
      source_name: item.source_name ?? '权威来源',
      review_state: 'PENDING_OWNER_REVIEW',
    }
  }
  return {
    ...common,
    projection_kind: 'FULL',
    facets: {
      engineering_objects: ['HIGHWAY'],
      specialties: [],
      equipment_domains: [],
      cross_type_tags: [],
    },
    source: { name: item.source_name ?? '权威来源', official: options.official ?? true },
    source_excerpt: {
      text: item.one_sentence_fact ?? `${item.title}的公开原文证据摘录。`,
      claim_ids: [acceptedClaimId],
      evidence_locators: ['html:p:1'],
    },
    ai_summary: {
      status: 'NOT_GENERATED',
      status_message: 'AI 总结尚未生成。已通过证据门禁的原文摘录仍可阅读。',
      body: null,
      claim_ids: [],
      judgment_paragraphs: [],
      model: null,
      generated_at: null,
    },
    claim_basis: ['AUTHORITY_FINDING'],
    hotspot: null,
    media: [],
    attachments: [],
    correction_alert: null,
  }
}

export function v2Feed(items: LegacyReaderItem[]) {
  return {
    items: items.map(item => v2Projection(item)),
    next_cursor: null,
    generated_at: '2026-07-19T01:00:00Z',
    projection_generation: 'v2',
  }
}

export function v2Appendix(eventId: string) {
  return {
    event_id: eventId,
    claims: [],
    evidence: [],
    automatic_results: [],
    relationships: [],
    automatic_relationships: [],
    corrections: [],
    review_context: null,
    review_href: '/review',
    content_summary: { total_items: 0, heavy_content: false, truncated_sections: [] },
  }
}

export async function mockV2Event(
  page: Page,
  item: LegacyReaderItem,
  options: { risk?: 'FULL' | 'R3_METADATA', official?: boolean } = {},
): Promise<void> {
  await page.route(`**/api/v2/events/${item.id}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(v2Projection(item, options)),
  }))
  await page.route(`**/api/v2/events/${item.id}/appendix`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(v2Appendix(item.id)),
  }))
}
