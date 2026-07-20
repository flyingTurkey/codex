import type { FeedPageV2 } from '@srbg/contracts'
import { describe, expect, it } from 'vitest'

import { toLegacyFeed } from '../app/composables/useIntelligenceFeed'


describe('T09 hotspot reader projection', () => {
  it('shows trigger, independent source count, and accepted-claim reasons without a score', () => {
    const eventId = '019f8400-0000-7000-8000-000000000301'
    const claimId = '019f8400-0000-7000-8000-000000000101'
    const page: FeedPageV2 = {
      items: [{
        projection_kind: 'FULL',
        event_id: eventId,
        title: '铁路隧道安全整治权威通报',
        primary_type: 'SAFETY_INTELLIGENCE',
        facets: {
          engineering_objects: ['RAILWAY', 'TUNNEL'],
          specialties: [], equipment_domains: [], cross_type_tags: [],
        },
        source: { name: '权威来源', official: true },
        human_reviewed: false,
        source_published_at: '2026-07-20T02:00:00Z',
        first_discovered_at: '2026-07-20T02:01:00Z',
        source_excerpt: {
          text: '权威材料记录了铁路隧道安全整治事实。',
          claim_ids: [claimId], evidence_locators: ['html:p:1'],
        },
        ai_summary: {
          status: 'NOT_GENERATED', body: null, paragraphs: [], claim_ids: [],
          judgment_paragraphs: [], model: null, generated_at: null,
        },
        original_url: 'https://example.gov.cn/t09/fixture',
        claim_basis: ['AUTHORITY_FINDING'],
        hotspot: {
          trigger: 'MULTI_SOURCE_7D', independent_source_count: 2,
          reasons: ['两份独立来源均有 AcceptedClaim 支持'],
        },
        media: [], attachments: [], correction_alert: null,
      }],
      next_cursor: null,
      generated_at: '2026-07-20T02:05:00Z',
      projection_generation: 'v2',
    }

    const item = toLegacyFeed(page).items[0]

    expect(item?.tags).toContain('HOTSPOT_AWARDED')
    expect(item?.relevance_reason).toBe(
      '7 天内多源触发；2 个独立来源；两份独立来源均有 AcceptedClaim 支持',
    )
    expect(item?.relevance_reason).not.toMatch(/总分|score|75/i)
  })
})
