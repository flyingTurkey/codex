import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it, vi } from 'vitest'

interface SourceCenterProjectionModule {
  candidateCanEnable?: (candidate: CandidateFixture, roles: readonly string[]) => boolean
  qualificationVerdictLabel?: (candidate: CandidateFixture) => string
  qualificationVerdictTone?: (candidate: CandidateFixture) => string
  workspaceViewOf?: (value: unknown) => 'attention' | 'candidates' | 'enabled'
}

interface WorkspaceModule {
  executeCandidateDecision?: (
    input: {
      candidateId: string
      decision: 'DISMISS' | 'ENABLE'
      expectedBundleSha256?: string
      reason: string
      waiverReason?: string
    },
    dependencies: {
      fetcher: (url: string, options: Record<string, unknown>) => Promise<unknown>
      idempotencyKey: () => string
      refresh: () => Promise<unknown>
    },
  ) => Promise<unknown>
  sourceWorkspaceEndpoint?: (
    view: 'attention' | 'candidates' | 'enabled',
    filters: Record<string, string | undefined>,
  ) => string
}

interface QualificationFixture {
  bundle_sha256: string
  candidate_id: string
  checks: Array<{
    code: string
    evidence_refs: string[]
    level: 'BLOCK' | 'PASS' | 'WARN'
    message: string
    observed_at: string
  }>
  created_at: string
  evidence_capture_policy: 'PRIVATE_RAW_ALLOWED' | 'TRANSIENT_METADATA_ONLY'
  expires_at: string
  id: string
  material_fingerprint: string
  reason_codes: string[]
  relevant_item_count: number
  rule_version: string
  run_id: string
  sampled_item_count: number
  storage_policy: 'METADATA_ONLY' | 'RAW_EVIDENCE_ALLOWED'
  verdict: 'BLOCKED' | 'QUALIFIED' | 'WARN_WAIVABLE'
}

interface CandidateFixture {
  available_actions: string[]
  authorization_boundary: string
  batch_enable_eligible: boolean
  canonical_url: string
  content_domains: string[]
  discovery_channels: string[]
  first_discovered_at: string
  id: string
  industries: string[]
  institution_name: string
  language_tags: string[]
  last_discovered_at: string
  latest_qualification: QualificationFixture | null
  occurrence_count: number
  status: string
}

type QualifiedCandidateFixture = CandidateFixture & {
  latest_qualification: QualificationFixture
}

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})
const projectionModules = import.meta.glob<SourceCenterProjectionModule>(
  '../app/source-cente[r].ts',
  { eager: true },
)
const workspaceModules = import.meta.glob<WorkspaceModule>(
  '../app/composables/useSourceCenterWorkspac[e].ts',
  { eager: true },
)

const qualifiedCandidate: QualifiedCandidateFixture = {
  available_actions: ['REQUEST_QUALIFICATION', 'ENABLE', 'DISMISS'],
  authorization_boundary: 'jtt.sc.gov.cn',
  batch_enable_eligible: true,
  canonical_url: 'https://jtt.sc.gov.cn/',
  content_domains: ['SAFETY_REGULATION'],
  discovery_channels: ['BAIDU_SEARCH', 'SITEMAP'],
  first_discovered_at: '2026-07-16T01:00:00Z',
  id: '019b1800-0000-7000-8000-000000000001',
  industries: ['BRIDGE'],
  institution_name: '四川省交通运输厅',
  language_tags: ['zh-CN'],
  last_discovered_at: '2026-07-17T01:00:00Z',
  latest_qualification: {
    bundle_sha256: 'b'.repeat(64),
    candidate_id: '019b1800-0000-7000-8000-000000000001',
    checks: [{
      code: 'PUBLIC_ACCESS_OK',
      evidence_refs: ['evidence:public-homepage'],
      level: 'PASS',
      message: '公开页面可访问且无需登录',
      observed_at: '2026-07-17T01:00:00Z',
    }],
    created_at: '2026-07-17T01:00:00Z',
    evidence_capture_policy: 'PRIVATE_RAW_ALLOWED',
    expires_at: '2026-07-24T01:00:00Z',
    id: '019b1800-0000-7000-8000-000000000011',
    material_fingerprint: 'a'.repeat(64),
    reason_codes: [],
    relevant_item_count: 5,
    rule_version: 'source-qualification-v1',
    run_id: '019b1800-0000-7000-8000-000000000021',
    sampled_item_count: 5,
    storage_policy: 'RAW_EVIDENCE_ALLOWED',
    verdict: 'QUALIFIED',
  },
  occurrence_count: 3,
  status: 'READY_FOR_DECISION',
}

const warningCandidate: QualifiedCandidateFixture = {
  ...qualifiedCandidate,
  batch_enable_eligible: false,
  id: '019b1800-0000-7000-8000-000000000002',
  latest_qualification: {
    ...qualifiedCandidate.latest_qualification,
    bundle_sha256: 'c'.repeat(64),
    checks: [{
      code: 'TERMS_NOT_PRESENT',
      evidence_refs: ['evidence:terms-probe'],
      level: 'WARN',
      message: '未检测到明确的公开使用条款',
      observed_at: '2026-07-17T01:00:00Z',
    }],
    reason_codes: ['TERMS_NOT_PRESENT'],
    storage_policy: 'METADATA_ONLY',
    verdict: 'WARN_WAIVABLE',
  },
}

const blockedCandidate: QualifiedCandidateFixture = {
  ...qualifiedCandidate,
  available_actions: ['REQUEST_QUALIFICATION', 'DISMISS'],
  batch_enable_eligible: false,
  id: '019b1800-0000-7000-8000-000000000003',
  latest_qualification: {
    ...qualifiedCandidate.latest_qualification,
    bundle_sha256: 'd'.repeat(64),
    reason_codes: ['ROBOTS_BLOCKED'],
    verdict: 'BLOCKED',
  },
}

function sourceCenterProjection(): SourceCenterProjectionModule {
  return projectionModules['../app/source-center.ts'] ?? {}
}

function workspaceModule(): WorkspaceModule {
  return workspaceModules['../app/composables/useSourceCenterWorkspace.ts'] ?? {}
}

describe('source automation workspace', () => {
  it('normalizes the three URL-backed views and fails unknown values to candidates', () => {
    const workspaceViewOf = sourceCenterProjection().workspaceViewOf
    expect(workspaceViewOf).toBeTypeOf('function')
    if (!workspaceViewOf) return

    expect(workspaceViewOf('candidates')).toBe('candidates')
    expect(workspaceViewOf('enabled')).toBe('enabled')
    expect(workspaceViewOf('attention')).toBe('attention')
    expect(workspaceViewOf('unknown')).toBe('candidates')
    expect(workspaceViewOf(['enabled'])).toBe('candidates')
  })

  it('maps qualification verdicts without conflating warning and block', () => {
    const { qualificationVerdictLabel, qualificationVerdictTone } = sourceCenterProjection()
    expect(qualificationVerdictLabel).toBeTypeOf('function')
    expect(qualificationVerdictTone).toBeTypeOf('function')
    if (!qualificationVerdictLabel || !qualificationVerdictTone) return

    expect(qualificationVerdictLabel(qualifiedCandidate)).toBe('资格通过')
    expect(qualificationVerdictTone(qualifiedCandidate)).toBe('healthy')
    expect(qualificationVerdictLabel(warningCandidate)).toBe('需单独豁免')
    expect(qualificationVerdictTone(warningCandidate)).toBe('degraded')
    expect(qualificationVerdictLabel(blockedCandidate)).toBe('硬阻断')
    expect(qualificationVerdictTone(blockedCandidate)).toBe('conflict')
  })

  it('allows only platform administrators to enable a server-authorized non-blocked candidate', () => {
    const candidateCanEnable = sourceCenterProjection().candidateCanEnable
    expect(candidateCanEnable).toBeTypeOf('function')
    if (!candidateCanEnable) return

    expect(candidateCanEnable(qualifiedCandidate, ['platform_admin'])).toBe(true)
    expect(candidateCanEnable(warningCandidate, ['platform_admin'])).toBe(true)
    expect(candidateCanEnable(qualifiedCandidate, ['source_admin'])).toBe(false)
    expect(candidateCanEnable(qualifiedCandidate, ['auditor'])).toBe(false)
    expect(candidateCanEnable(blockedCandidate, ['platform_admin'])).toBe(false)
    expect(candidateCanEnable({
      ...qualifiedCandidate,
      latest_qualification: null,
    }, ['platform_admin'])).toBe(false)
  })

  it('renders keyboard-addressable candidate, enabled and attention tabs', async () => {
    const SourceWorkspaceTabs
      = componentModules['../app/components/SourceWorkspaceTabs.vue']?.default
    expect(SourceWorkspaceTabs).toBeDefined()
    if (!SourceWorkspaceTabs) return

    const wrapper = mount(SourceWorkspaceTabs, {
      props: {
        activeView: 'candidates',
        counts: { attention: 2, candidates: 9, enabled: 4 },
      },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs).toHaveLength(3)
    expect(tabs.map(tab => tab.attributes('aria-label'))).toEqual([
      '候选来源 9',
      '已启用来源 4',
      '需处理 2',
    ])
    expect(tabs[0]?.attributes('aria-selected')).toBe('true')
    expect(tabs[1]?.attributes('tabindex')).toBe('-1')

    await tabs[1]?.trigger('click')
    expect(wrapper.emitted('change')).toEqual([['enabled']])
  })

  it('keeps final candidate decisions out of the source administrator UI', () => {
    const SourceCandidateCard
      = componentModules['../app/components/SourceCandidateCard.vue']?.default
    expect(SourceCandidateCard).toBeDefined()
    if (!SourceCandidateCard) return

    const sourceAdmin = mount(SourceCandidateCard, {
      props: { candidate: qualifiedCandidate, roles: ['source_admin'] },
    })
    expect(sourceAdmin.text()).toContain('重新资格审核')
    expect(sourceAdmin.find('button[data-decision="ENABLE"]').exists()).toBe(false)
    expect(sourceAdmin.find('input[type="checkbox"]').exists()).toBe(false)

    const platformAdmin = mount(SourceCandidateCard, {
      props: { candidate: qualifiedCandidate, roles: ['platform_admin'] },
    })
    expect(platformAdmin.get('button[data-decision="ENABLE"]').text()).toBe('启用')
    expect(platformAdmin.get('input[type="checkbox"]').attributes('aria-label')).toContain(
      qualifiedCandidate.institution_name,
    )

    const blocked = mount(SourceCandidateCard, {
      props: { candidate: blockedCandidate, roles: ['platform_admin'] },
    })
    expect(blocked.find('button[data-decision="ENABLE"]').exists()).toBe(false)
    expect(blocked.find('input[type="checkbox"]').exists()).toBe(false)

    const failedWithoutBundle = mount(SourceCandidateCard, {
      props: {
        candidate: { ...blockedCandidate, latest_qualification: null },
        roles: ['platform_admin'],
      },
    })
    expect(failedWithoutBundle.get('button[data-decision="DISMISS"]').text()).toBe('不启用')
    expect(failedWithoutBundle.find('button[data-decision="ENABLE"]').exists()).toBe(false)

    const awaitingQualification = mount(SourceCandidateCard, {
      props: {
        candidate: { ...qualifiedCandidate, latest_qualification: null },
        roles: ['source_admin'],
      },
    })
    expect(awaitingQualification.text()).toContain('证据策略待定')
    expect(awaitingQualification.text()).not.toContain('私有原始证据')
  })

  it('submits qualified enable and dismiss decisions without a typed audit reason', async () => {
    const SourceCandidateDrawer
      = componentModules['../app/components/SourceCandidateDrawer.vue']?.default
    expect(SourceCandidateDrawer).toBeDefined()
    if (!SourceCandidateDrawer) return

    const enable = mount(SourceCandidateDrawer, {
      props: {
        candidate: qualifiedCandidate,
        initialDecision: 'ENABLE',
        modelValue: true,
        roles: ['platform_admin'],
      },
    })
    expect(enable.find('textarea[name="decision-reason"]').exists()).toBe(false)
    await enable.get('button[data-submit-decision]').trigger('click')
    expect(enable.emitted('decision')).toEqual([[
      {
        decision: 'ENABLE',
        reason: '启用当前服务端资格审核通过的候选来源',
      },
    ]])

    const dismiss = mount(SourceCandidateDrawer, {
      props: {
        candidate: qualifiedCandidate,
        initialDecision: 'DISMISS',
        modelValue: true,
        roles: ['platform_admin'],
      },
    })
    expect(dismiss.find('textarea[name="decision-reason"]').exists()).toBe(false)
    await dismiss.get('button[data-submit-decision]').trigger('click')
    expect(dismiss.emitted('decision')).toEqual([[
      {
        decision: 'DISMISS',
        reason: '不启用当前候选来源',
      },
    ]])
  })

  it('requires only an explicit waiver reason for a warning and never enables a block', async () => {
    const SourceCandidateDrawer
      = componentModules['../app/components/SourceCandidateDrawer.vue']?.default
    expect(SourceCandidateDrawer).toBeDefined()
    if (!SourceCandidateDrawer) return

    const warning = mount(SourceCandidateDrawer, {
      props: {
        candidate: warningCandidate,
        initialDecision: 'ENABLE',
        modelValue: true,
        roles: ['platform_admin'],
      },
    })
    expect(warning.text()).toContain('未检测到明确的公开使用条款')
    expect(warning.get('button[data-select-decision="ENABLE"]').attributes('aria-pressed')).toBe('true')
    const submit = warning.get('button[data-submit-decision]')
    expect(submit.attributes('disabled')).toBeDefined()
    expect(warning.find('textarea[name="decision-reason"]').exists()).toBe(false)
    await warning.get('textarea[name="waiver-reason"]').setValue(
      '只展示题录、必要短摘要和原文链接',
    )
    expect(submit.attributes('disabled')).toBeUndefined()
    await submit.trigger('click')
    expect(warning.emitted('decision')).toEqual([[
      {
        decision: 'ENABLE',
        reason: '豁免警告并启用当前候选来源',
        waiverReason: '只展示题录、必要短摘要和原文链接',
      },
    ]])

    const blocked = mount(SourceCandidateDrawer, {
      props: {
        candidate: blockedCandidate,
        modelValue: true,
        roles: ['platform_admin'],
      },
    })
    expect(blocked.find('button[data-select-decision="ENABLE"]').exists()).toBe(false)
    expect(blocked.text()).toContain('硬阻断不能由管理员绕过')
  })

  it('sends cursor and filters to the server endpoint for every workspace view', () => {
    const sourceWorkspaceEndpoint = workspaceModule().sourceWorkspaceEndpoint
    expect(sourceWorkspaceEndpoint).toBeTypeOf('function')
    if (!sourceWorkspaceEndpoint) return

    const candidateUrl = new URL(sourceWorkspaceEndpoint('candidates', {
      content_domain: 'SAFETY_REGULATION',
      cursor: 'next page',
      industry: 'BRIDGE',
      q: '四川 桥梁',
      status: 'READY_FOR_DECISION',
    }), 'https://ui.test')
    expect(candidateUrl.pathname).toBe('/api/v1/admin/source-candidates')
    expect(Object.fromEntries(candidateUrl.searchParams)).toEqual({
      content_domain: 'SAFETY_REGULATION',
      cursor: 'next page',
      industry: 'BRIDGE',
      q: '四川 桥梁',
      status: 'READY_FOR_DECISION',
    })

    expect(sourceWorkspaceEndpoint('enabled', {
      content_domain: 'SAFETY_REGULATION',
      cursor: 'enabled-next-page',
      q: '交通运输厅',
      status: 'ACTIVE',
    })).toBe('/api/v1/admin/source-streams?cursor=enabled-next-page&q=%E4%BA%A4%E9%80%9A%E8%BF%90%E8%BE%93%E5%8E%85')
    expect(sourceWorkspaceEndpoint('attention', {
      cursor: 'attention-next-page',
      q: 'ignored',
      status: 'PAUSED',
    })).toBe('/api/v1/admin/source-attention?cursor=attention-next-page')
  })

  it('refreshes a stale qualification once without retrying the decision', async () => {
    const executeCandidateDecision = workspaceModule().executeCandidateDecision
    expect(executeCandidateDecision).toBeTypeOf('function')
    if (!executeCandidateDecision) return

    const staleProblem = {
      data: {
        detail: 'qualification bundle changed',
        status: 409,
        title: 'Qualification bundle is stale',
        type: 'https://srbg.example/problems/stale-qualification-bundle',
      },
      statusCode: 409,
    }
    const fetcher = vi.fn().mockRejectedValue(staleProblem)
    const refresh = vi.fn().mockResolvedValue(undefined)

    await expect(executeCandidateDecision({
      candidateId: qualifiedCandidate.id,
      decision: 'ENABLE',
      expectedBundleSha256: qualifiedCandidate.latest_qualification.bundle_sha256,
      reason: '启用当前全绿资格包',
    }, {
      fetcher,
      idempotencyKey: () => '019b1800-0000-7000-8000-000000000099',
      refresh,
    })).rejects.toBe(staleProblem)

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('binds decision body and idempotency key to the current qualification bundle', async () => {
    const executeCandidateDecision = workspaceModule().executeCandidateDecision
    expect(executeCandidateDecision).toBeTypeOf('function')
    if (!executeCandidateDecision) return

    const fetcher = vi.fn().mockResolvedValue({ status: 'ENABLED' })
    const refresh = vi.fn().mockResolvedValue(undefined)
    await executeCandidateDecision({
      candidateId: warningCandidate.id,
      decision: 'ENABLE',
      expectedBundleSha256: warningCandidate.latest_qualification.bundle_sha256,
      reason: '启用受限题录来源',
      waiverReason: '只展示题录、必要短摘要和原文链接',
    }, {
      fetcher,
      idempotencyKey: () => '019b1800-0000-7000-8000-000000000098',
      refresh,
    })

    expect(fetcher).toHaveBeenCalledWith(
      `/api/v1/admin/source-candidates/${warningCandidate.id}/decisions`,
      {
        body: {
          decision: 'ENABLE',
          expected_bundle_sha256: warningCandidate.latest_qualification.bundle_sha256,
          reason: '启用受限题录来源',
          waiver_reason: '只展示题录、必要短摘要和原文链接',
        },
        headers: { 'Idempotency-Key': '019b1800-0000-7000-8000-000000000098' },
        method: 'POST',
        retry: 0,
        timeout: 5_000,
      },
    )
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('can dismiss a failed candidate without inventing a qualification bundle hash', async () => {
    const executeCandidateDecision = workspaceModule().executeCandidateDecision
    expect(executeCandidateDecision).toBeTypeOf('function')
    if (!executeCandidateDecision) return

    const fetcher = vi.fn().mockResolvedValue({ status: 'DISMISSED' })
    const refresh = vi.fn().mockResolvedValue(undefined)
    await executeCandidateDecision({
      candidateId: blockedCandidate.id,
      decision: 'DISMISS',
      reason: '不启用当前候选来源',
    }, {
      fetcher,
      idempotencyKey: () => '019b1800-0000-7000-8000-000000000097',
      refresh,
    })

    expect(fetcher).toHaveBeenCalledWith(
      `/api/v1/admin/source-candidates/${blockedCandidate.id}/decisions`,
      {
        body: {
          decision: 'DISMISS',
          reason: '不启用当前候选来源',
        },
        headers: { 'Idempotency-Key': '019b1800-0000-7000-8000-000000000097' },
        method: 'POST',
        retry: 0,
        timeout: 5_000,
      },
    )
    const options = fetcher.mock.calls[0]?.[1] as { body?: Record<string, unknown> }
    expect(options.body).not.toHaveProperty('expected_bundle_sha256')
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('rewires the source list page to server-backed automation queues', () => {
    const page = readFileSync(
      resolve(process.cwd(), 'app/pages/admin/sources/index.vue'),
      'utf8',
    )
    const composable = readFileSync(
      resolve(process.cwd(), 'app/composables/useSourceCenterWorkspace.ts'),
      'utf8',
    )

    expect(page).toContain('SourceWorkspaceTabs')
    expect(page).toContain('SourceCandidateCard')
    expect(page).toContain('SourceCandidateDrawer')
    expect(page).toContain('useSourceCenterWorkspace')
    expect(composable).toContain('/api/v1/admin/source-candidates')
    expect(composable).toContain('/api/v1/admin/source-streams')
    expect(composable).toContain('/api/v1/admin/source-attention')
    expect(page).not.toContain('filteredSources')
    expect(page).not.toContain('登记候选来源')
  })
})
