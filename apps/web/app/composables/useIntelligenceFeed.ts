import type { FeedPage } from '@srbg/contracts'
import type { MaybeRef } from 'vue'
import { computed, toValue } from 'vue'

export type FeedContentTypeFilter = 'all' | 'SAFETY_REGULATION' | 'SAFETY_CASE'

export interface FeedContentTypeOption {
  readonly label: string
  readonly value: FeedContentTypeFilter
}

export function useIntelligenceFeed(
  mode: 'selected' | 'all',
  domain?: 'safety' | 'digital',
  contentType: MaybeRef<FeedContentTypeFilter> = 'all',
) {
  const query = computed(() => {
    const selectedType = toValue(contentType)
    return {
      mode,
      domain,
      content_type: selectedType === 'all' ? undefined : selectedType,
      sort: 'latest',
    }
  })

  return useFetch<FeedPage>('/api/v1/feed', {
    key: computed(() => `feed:${mode}:${domain ?? 'all'}:${toValue(contentType)}`),
    query,
    server: false,
    retry: 0,
    timeout: 5_000,
  })
}
