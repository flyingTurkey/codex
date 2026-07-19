import type { EventFullProjectionV2, EventMetadataProjectionV2, FeedPage, FeedPageV2 } from '@srbg/contracts'
import type { MaybeRef } from 'vue'
import { computed, ref, toValue } from 'vue'

export type FeedContentTypeFilter = 'all' | 'DIGITAL_TRANSFORMATION' | 'SAFETY_INTELLIGENCE' | 'INDUSTRY_UPDATE'
  | 'DIGITAL_CASE' | 'JOURNAL_PAPER' | 'SOFTWARE_PRODUCT' | 'IOT_PRODUCT'
  | 'LOW_ALTITUDE_EQUIPMENT' | 'AI_EQUIPMENT' | 'SAFETY_REGULATION' | 'SAFETY_CASE'
export interface DigitalFeedFilters {
  readonly engineering_domain?: string
  readonly scenario?: string
  readonly maturity?: string
  readonly source_nature?: string
  readonly paper_type?: string
  readonly technology_tag?: string
  readonly access_level?: string
  readonly year?: number | string
  readonly product_kind?: string
  readonly evidence_level?: string
  readonly deployment_mode?: string
  readonly sort?: 'latest' | 'relevance'
}
export interface FeedContentTypeOption { readonly label: string, readonly value: FeedContentTypeFilter }

export function toLegacyFeed(page: FeedPageV2): FeedPage {
  const items = page.items.map((projection): FeedPage['items'][number] => {
    const full = projection.projection_kind === 'FULL' ? projection as EventFullProjectionV2 : null
    const metadata = projection as EventMetadataProjectionV2
    const safety = projection.primary_type === 'SAFETY_INTELLIGENCE'
    const excerpt = full?.source_excerpt.text
    const summary = full?.ai_summary.status === 'SUCCEEDED' ? full.ai_summary.body : undefined
    return {
      id: projection.event_id,
      publication_revision_id: null,
      domain: safety ? 'SAFETY' : 'DIGITAL',
      content_type: safety ? 'SAFETY_CASE' : 'DIGITAL_CASE',
      title: projection.title,
      source_name: full?.source.name ?? metadata.source_name,
      source_published_at: projection.source_published_at,
      first_discovered_at: projection.first_discovered_at,
      activity_at: projection.source_published_at ?? projection.first_discovered_at,
      original_url: projection.original_url,
      review_status: full ? 'APPROVED' : 'PENDING',
      one_sentence_fact: excerpt,
      relevance_reason: full?.hotspot?.reasons.join('；'),
      detail_available: Boolean(full),
      tags: full ? [projection.primary_type, ...(full.facets?.engineering_objects ?? [])] : [projection.primary_type],
      ai_assistance: full
        ? {
            status: full.ai_summary.status === 'SUCCEEDED' ? 'ASSISTED' : 'DEGRADED',
            model_profile: full.ai_summary.model,
            generated_at: full.ai_summary.generated_at,
            accepted_claims_only: (full.ai_summary.claim_ids ?? []).length > 0,
          }
        : undefined,
      ai_judgment: summary
        ? {
            why_worth_attention: summary,
            used_claim_ids: full?.ai_summary.claim_ids ?? [],
            potential_industry_impacts: [], potential_engineering_scenarios: [],
            current_limitations: [], questions_to_verify: [],
          }
        : undefined,
      event_type: safety ? 'SAFETY_INCIDENT' : 'DIGITAL_PROJECT',
      event_status: 'ACTIVE',
      canonical_event_id: projection.event_id,
      event_version: 1,
    }
  })
  return {
    items,
    next_cursor: page.next_cursor ?? null,
    fingerprint: `projection-${page.projection_generation}`,
    generated_at: page.generated_at,
    freshness: 'fresh', notices: [],
  }
}

function selectedPrimaryType(selected: FeedContentTypeFilter): string | undefined {
  if (selected === 'all') return undefined
  if (selected === 'SAFETY_CASE' || selected === 'SAFETY_REGULATION') return 'SAFETY_INTELLIGENCE'
  if (['DIGITAL_CASE', 'JOURNAL_PAPER', 'SOFTWARE_PRODUCT', 'IOT_PRODUCT', 'LOW_ALTITUDE_EQUIPMENT', 'AI_EQUIPMENT'].includes(selected)) return 'DIGITAL_TRANSFORMATION'
  return selected
}

export function useIntelligenceFeed(
  mode: MaybeRef<'selected' | 'all'>,
  domain?: 'safety' | 'digital' | 'industry',
  contentType: MaybeRef<FeedContentTypeFilter> = 'all',
  _digitalFilters: MaybeRef<DigitalFeedFilters> = {},
) {
  const primaryType = computed(() => selectedPrimaryType(toValue(contentType))
    ?? (domain === 'safety' ? 'SAFETY_INTELLIGENCE' : domain === 'industry' ? 'INDUSTRY_UPDATE' : domain === 'digital' ? 'DIGITAL_TRANSFORMATION' : undefined))
  const query = computed(() => ({ mode: toValue(mode), primary_type: primaryType.value }))
  const raw = useFetch<FeedPageV2>('/api/v2/feed', {
    key: computed(() => `feed-v2:${toValue(mode)}:${primaryType.value ?? 'all'}`),
    query, server: false, retry: 0, timeout: 5_000,
  })
  const data = computed<FeedPage | null>(() => raw.data.value ? toLegacyFeed(raw.data.value) : null)
  const loadingMore = ref(false)
  async function loadMore(): Promise<void> {
    const current = raw.data.value
    if (!current?.next_cursor || loadingMore.value) return
    loadingMore.value = true
    try {
      const next = await $fetch<FeedPageV2>('/api/v2/feed', { query: { ...query.value, cursor: current.next_cursor }, timeout: 5_000 })
      raw.data.value = { ...next, items: [...current.items, ...next.items] }
    }
    finally { loadingMore.value = false }
  }
  return { ...raw, data, loadingMore, loadMore }
}
