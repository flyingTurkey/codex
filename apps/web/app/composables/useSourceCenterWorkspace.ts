import type { SourceCandidateDecision, SourceCandidateDecisionRequest } from '@srbg/contracts'
import { computed, reactive, ref } from 'vue'

import type { SourceWorkspaceView } from '../source-center'
import { workspaceViewOf } from '../source-center'
import { createUuidV7 } from '../utils/uuid-v7'

export interface SourceWorkspaceFilters {
  content_domain?: string
  cursor?: string
  discovery_channel?: string
  industry?: string
  language_tag?: string
  q?: string
  status?: string
  verdict?: string
}

export interface CandidateDecisionInput {
  candidateId: string
  decision: SourceCandidateDecision
  expectedBundleSha256?: string
  reason: string
  waiverReason?: string
}

interface CandidateDecisionDependencies {
  readonly fetcher: (url: string, options: Record<string, unknown>) => Promise<unknown>
  readonly idempotencyKey: () => string
  readonly refresh: () => Promise<unknown>
}

const workspacePaths: Readonly<Record<SourceWorkspaceView, string>> = {
  attention: '/api/v1/admin/source-attention',
  candidates: '/api/v1/admin/source-candidates',
  enabled: '/api/v1/admin/source-streams',
}

const workspaceFilterKeys: Readonly<Record<SourceWorkspaceView, ReadonlySet<string>>> = {
  attention: new Set(['cursor']),
  candidates: new Set([
    'content_domain',
    'cursor',
    'discovery_channel',
    'industry',
    'language_tag',
    'q',
    'status',
    'verdict',
  ]),
  enabled: new Set(['cursor', 'q']),
}

export function sourceWorkspaceEndpoint(
  view: SourceWorkspaceView,
  filters: Readonly<Record<string, string | undefined>>,
): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters).sort(([left], [right]) => (
    left.localeCompare(right)
  ))) {
    if (!workspaceFilterKeys[view].has(key)) continue
    const normalized = value?.trim()
    if (normalized) query.set(key, normalized)
  }
  const serialized = query.toString()
  return serialized ? `${workspacePaths[view]}?${serialized}` : workspacePaths[view]
}

function requestStatus(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) return undefined
  if ('statusCode' in error && typeof error.statusCode === 'number') return error.statusCode
  if (!('data' in error) || typeof error.data !== 'object' || error.data === null) return undefined
  return 'status' in error.data && typeof error.data.status === 'number'
    ? error.data.status
    : undefined
}

/**
 * Submit exactly once. A stale bundle triggers a list refresh so the administrator can
 * review the new evidence; the old decision is never retried automatically.
 */
export async function executeCandidateDecision(
  input: CandidateDecisionInput,
  dependencies: CandidateDecisionDependencies,
): Promise<unknown> {
  const body: SourceCandidateDecisionRequest = {
    decision: input.decision,
    reason: input.reason.trim(),
    ...(input.expectedBundleSha256
      ? { expected_bundle_sha256: input.expectedBundleSha256 }
      : {}),
    ...(input.waiverReason?.trim()
      ? { waiver_reason: input.waiverReason.trim() }
      : {}),
  }
  try {
    const result = await dependencies.fetcher(
      `/api/v1/admin/source-candidates/${input.candidateId}/decisions`,
      {
        body,
        headers: { 'Idempotency-Key': dependencies.idempotencyKey() },
        method: 'POST',
        retry: 0,
        timeout: 5_000,
      },
    )
    await dependencies.refresh()
    return result
  } catch (error) {
    if (requestStatus(error) === 409) await dependencies.refresh()
    throw error
  }
}

export function useSourceCenterWorkspace(initialView: unknown = 'candidates') {
  const activeView = ref<SourceWorkspaceView>(workspaceViewOf(initialView))
  const cursor = ref('')
  const filters = reactive<Omit<SourceWorkspaceFilters, 'cursor'>>({
    content_domain: '',
    discovery_channel: '',
    industry: '',
    language_tag: '',
    q: '',
    status: '',
    verdict: '',
  })
  const endpoint = computed(() => sourceWorkspaceEndpoint(activeView.value, {
    ...filters,
    cursor: cursor.value,
  }))

  function changeView(view: SourceWorkspaceView): void {
    activeView.value = view
    cursor.value = ''
  }

  function resetCursor(): void {
    cursor.value = ''
  }

  function candidateDecision(
    input: CandidateDecisionInput,
    dependencies: Omit<CandidateDecisionDependencies, 'idempotencyKey'>,
  ): Promise<unknown> {
    return executeCandidateDecision(input, {
      ...dependencies,
      idempotencyKey: createUuidV7,
    })
  }

  return {
    activeView,
    candidateDecision,
    changeView,
    cursor,
    endpoint,
    filters,
    resetCursor,
  }
}
