import type { FeedPage } from '@srbg/contracts'

export function useIntelligenceFeed(
  mode: 'selected' | 'all',
  domain?: 'safety' | 'digital',
) {
  return useFetch<FeedPage>('/api/v1/feed', {
    key: `feed:${mode}:${domain ?? 'all'}`,
    query: { mode, domain, sort: 'latest' },
    server: false,
    retry: 0,
    timeout: 5_000,
  })
}
