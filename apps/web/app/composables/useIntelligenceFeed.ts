import type { FeedPage } from '@srbg/contracts'
import type { MaybeRef } from 'vue'
import { computed, toValue } from 'vue'

export type FeedContentTypeFilter =
  | 'all'
  | 'DIGITAL_CASE'
  | 'JOURNAL_PAPER'
  | 'SOFTWARE_PRODUCT'
  | 'IOT_PRODUCT'
  | 'LOW_ALTITUDE_EQUIPMENT'
  | 'AI_EQUIPMENT'
  | 'SAFETY_REGULATION'
  | 'SAFETY_CASE'

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

export interface FeedContentTypeOption {
  readonly label: string
  readonly value: FeedContentTypeFilter
}

export function useIntelligenceFeed(
  mode: MaybeRef<'selected' | 'all'>,
  domain?: 'safety' | 'digital',
  contentType: MaybeRef<FeedContentTypeFilter> = 'all',
  digitalFilters: MaybeRef<DigitalFeedFilters> = {},
) {
  const query = computed(() => {
    const selectedType = toValue(contentType)
    const filters = toValue(digitalFilters)
    return {
      mode: toValue(mode),
      domain,
      content_type: selectedType === 'all' ? undefined : selectedType,
      engineering_domain: filters.engineering_domain === 'all' ? undefined : filters.engineering_domain,
      scenario: filters.scenario === 'all' ? undefined : filters.scenario,
      maturity: filters.maturity === 'all' ? undefined : filters.maturity,
      source_nature: filters.source_nature === 'all' ? undefined : filters.source_nature,
      paper_type: filters.paper_type === 'all' ? undefined : filters.paper_type,
      technology_tag: filters.technology_tag === 'all' ? undefined : filters.technology_tag,
      access_level: filters.access_level === 'all' ? undefined : filters.access_level,
      year: filters.year === 'all' || filters.year === '' ? undefined : filters.year,
      product_kind: filters.product_kind === 'all' ? undefined : filters.product_kind,
      evidence_level: filters.evidence_level === 'all' ? undefined : filters.evidence_level,
      deployment_mode: filters.deployment_mode === 'all' ? undefined : filters.deployment_mode,
      sort: filters.sort ?? 'latest',
    }
  })

  return useFetch<FeedPage>('/api/v1/feed', {
    key: computed(() => `feed:${toValue(mode)}:${domain ?? 'all'}:${toValue(contentType)}:${JSON.stringify(toValue(digitalFilters))}`),
    query,
    server: false,
    retry: 0,
    timeout: 5_000,
  })
}
