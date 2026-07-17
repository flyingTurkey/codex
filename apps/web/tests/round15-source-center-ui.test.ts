import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

import {
  safeConnectorConfigRows,
  shanghaiLocalDateTimeToUtc,
  sourceSloPayload,
} from '../app/source-center'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const navigationModules = import.meta.glob<{
  adminNavigationForRoles?: (roles: readonly string[]) => readonly { id: string, to: string }[]
}>('../app/navigatio[n].ts', { eager: true })

function appSource(path: string): string {
  return readFileSync(resolve(process.cwd(), 'app', path), 'utf8')
}

describe('round 15 source center V2 UI', () => {
  it('converts governance datetime-local values from Asia/Shanghai to UTC', () => {
    expect(shanghaiLocalDateTimeToUtc('2026-07-16T12:34')).toBe(
      '2026-07-16T04:34:00.000Z',
    )
    expect(shanghaiLocalDateTimeToUtc('2026-01-01T00:15:30')).toBe(
      '2025-12-31T16:15:30.000Z',
    )
    expect(() => shanghaiLocalDateTimeToUtc('2026-02-30T12:00')).toThrow(
      'invalid Asia/Shanghai local date-time',
    )
  })

  it('projects lifecycle commands exclusively from server available_actions', async () => {
    const SourceLifecycleControls
      = componentModules['../app/components/SourceLifecycleControls.vue']?.default

    expect(SourceLifecycleControls).toBeDefined()
    if (!SourceLifecycleControls) return

    const wrapper = mount(SourceLifecycleControls, {
      props: {
        availableActions: ['PAUSE', 'RETIRE'],
        lifecycleState: 'ACTIVE',
      },
    })

    expect(wrapper.get('button[data-action="PAUSE"]').text()).toContain('暂停')
    expect(wrapper.get('button[data-action="RETIRE"]').text()).toContain('退役')
    expect(wrapper.find('button[data-action="RESUME"]').exists()).toBe(false)
    expect(wrapper.find('button[data-action="APPROVE_PRODUCTION"]').exists()).toBe(false)

    await wrapper.get('button[data-action="PAUSE"]').trigger('click')
    await wrapper.get('textarea[name="action-reason"]').setValue('合规证据到期，暂停复核')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('command')).toEqual([
      [{ action: 'PAUSE', reason: '合规证据到期，暂停复核' }],
    ])
  })

  it('keeps connector configuration declarative and preview-only', async () => {
    const ConnectorConfigEditor
      = componentModules['../app/components/ConnectorConfigEditor.vue']?.default

    expect(ConnectorConfigEditor).toBeDefined()
    if (!ConnectorConfigEditor) return

    const wrapper = mount(ConnectorConfigEditor, {
      props: {
        definitions: [
          { connectorType: 'RSS_ATOM', definitionVersion: '1.0.0', label: 'RSS / Atom' },
          { connectorType: 'JSON_API', definitionVersion: '1.0.0', label: 'JSON API' },
        ],
      },
    })

    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.find('input[type="password"]').exists()).toBe(false)
    expect(wrapper.get('[role="note"]').text()).toContain('不会发起网络采集')

    await wrapper.get('select[name="connector-type"]').setValue('RSS_ATOM')
    await wrapper.get('input[name="feed-url"]').setValue('https://example.test/feed.xml')
    await wrapper.get('input[name="allowed-hosts"]').setValue('example.test')
    await wrapper.get('input[name="credential-ref"]').setValue('vault://source-connectors/rss-token')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('preview')).toEqual([
      [{
        config: {
          allowed_hosts: ['example.test'],
          credential_ref: 'vault://source-connectors/rss-token',
          feed_url: 'https://example.test/feed.xml',
        },
        connector_type: 'RSS_ATOM',
        definition_version: '1.0.0',
      }],
    ])
  })

  it('requires an accepted Fixture upload before completing a pending replay', async () => {
    const SourceFixtureTrialControls
      = componentModules['../app/components/SourceFixtureTrialControls.vue']?.default

    expect(SourceFixtureTrialControls).toBeDefined()
    if (!SourceFixtureTrialControls) return

    const wrapper = mount(SourceFixtureTrialControls, {
      props: {
        busy: false,
        uploaded: false,
      },
    })

    const completionButton = wrapper.get('button[data-action="complete-fixture"]')
    expect(completionButton.attributes('disabled')).toBeDefined()

    const file = new File(['<html><body>fixed fixture</body></html>'], 'fixture.html', {
      type: 'text/html',
    })
    Object.defineProperty(wrapper.get('input[name="fixture-file"]').element, 'files', {
      configurable: true,
      value: [file],
    })
    await wrapper.get('input[name="fixture-file"]').trigger('change')
    await wrapper.get('input[name="fixture-canonical-url"]').setValue(
      'https://example.test/notices/fixture',
    )
    await wrapper.get('form[data-form="fixture-upload"]').trigger('submit')

    expect(wrapper.emitted('upload')).toEqual([[
      {
        canonicalUrl: 'https://example.test/notices/fixture',
        file,
      },
    ]])

    await wrapper.setProps({ uploaded: true })
    expect(wrapper.get('input[name="fixture-file"]').attributes('disabled')).toBeUndefined()
    const detailFile = new File(['<html><body>fixed detail</body></html>'], 'detail.html', {
      type: 'text/html',
    })
    Object.defineProperty(wrapper.get('input[name="fixture-file"]').element, 'files', {
      configurable: true,
      value: [detailFile],
    })
    await wrapper.get('input[name="fixture-file"]').trigger('change')
    await wrapper.get('input[name="fixture-canonical-url"]').setValue(
      'https://example.test/notices/fixture-detail',
    )
    await wrapper.get('form[data-form="fixture-upload"]').trigger('submit')
    expect(wrapper.emitted('upload')?.[1]).toEqual([
      {
        canonicalUrl: 'https://example.test/notices/fixture-detail',
        file: detailFile,
      },
    ])

    await wrapper.get('input[name="fixture-completion-reason"]').setValue(
      '固定样本已完成安全回放',
    )
    await wrapper.get('form[data-form="fixture-complete"]').trigger('submit')
    expect(wrapper.emitted('complete')).toEqual([[
      { reason: '固定样本已完成安全回放' },
    ]])
  })

  it('renders only non-sensitive declarative connector fields', () => {
    const rows = safeConnectorConfigRows({
      allowed_hosts: ['example.test'],
      api_token: 'must-never-render',
      credential_ref: '[configured]',
      feed_url: 'https://example.test/feed.xml',
      headers: {
        Accept: 'application/rss+xml',
        Authorization: 'Bearer must-never-render',
      },
    })

    expect(rows).toEqual([
      { label: 'allowed_hosts', value: 'example.test' },
      { label: 'feed_url', value: 'https://example.test/feed.xml' },
      { label: 'headers.Accept', value: 'application/rss+xml' },
    ])
    expect(JSON.stringify(rows)).not.toContain('credential_ref')
    expect(JSON.stringify(rows)).not.toContain('must-never-render')
  })

  it('fails closed when an applicable source SLO lacks either explicit confirmation', () => {
    expect(sourceSloPayload({
      applicability: 'APPLICABLE',
      authorizationConfirmed: false,
      reason: '',
      targetMinutes: 15,
      technicalConditionsConfirmed: true,
    })).toBeNull()
    expect(sourceSloPayload({
      applicability: 'APPLICABLE',
      authorizationConfirmed: true,
      reason: '',
      targetMinutes: 15,
      technicalConditionsConfirmed: true,
    })).toEqual({
      applicability: 'APPLICABLE',
      authorization_confirmed: true,
      target_minutes: 15,
      technical_conditions_confirmed: true,
    })
    expect(sourceSloPayload({
      applicability: 'NOT_APPLICABLE',
      authorizationConfirmed: true,
      reason: '来源授权或技术条件不满足',
      targetMinutes: 15,
      technicalConditionsConfirmed: true,
    })).toEqual({
      applicability: 'NOT_APPLICABLE',
      authorization_confirmed: false,
      reason: '来源授权或技术条件不满足',
      technical_conditions_confirmed: false,
    })
  })

  it('renders a five-dimensional coverage matrix with explicit gaps', () => {
    const SourceCoverageMatrix
      = componentModules['../app/components/SourceCoverageMatrix.vue']?.default

    expect(SourceCoverageMatrix).toBeDefined()
    if (!SourceCoverageMatrix) return

    const wrapper = mount(SourceCoverageMatrix, {
      props: {
        cells: [
          {
            active_count: 1,
            candidate_count: 2,
            content_domain: 'SAFETY_REGULATION',
            gap: false,
            industry: 'BRIDGE',
            language: 'zh-CN',
            region: 'CN-SC',
            source_type: 'government',
            trial_count: 1,
          },
          {
            active_count: 0,
            candidate_count: 1,
            content_domain: 'ACCIDENT_INVESTIGATION',
            gap: true,
            industry: 'TUNNEL',
            language: 'zh-CN',
            region: 'CN-SC',
            source_type: 'government',
            trial_count: 0,
          },
        ],
      },
    })

    expect(wrapper.get('table').attributes('aria-label')).toBe('来源覆盖矩阵')
    expect(wrapper.text()).toContain('工程行业')
    expect(wrapper.text()).toContain('内容域')
    expect(wrapper.text()).toContain('来源类型')
    expect(wrapper.text()).toContain('地区 / 语言')
    expect(wrapper.text()).toContain('桥梁')
    expect(wrapper.text()).toContain('安全规定')
    expect(wrapper.text()).toContain('隧道')
    expect(wrapper.text()).toContain('事故调查')
    expect(wrapper.text()).toContain('缺口')
    expect(wrapper.text()).not.toContain('网址总数')
  })

  it('filters source-center navigation by role while keeping auditors read-only', () => {
    const navigation = navigationModules['../app/navigation.ts']
    const navigationForRoles = navigation?.adminNavigationForRoles

    expect(navigationForRoles).toBeTypeOf('function')
    if (!navigationForRoles) return

    expect(navigationForRoles(['source_admin']).map(item => item.id)).toContain('sources')
    expect(navigationForRoles(['platform_admin']).map(item => item.id)).toContain('sources')
    expect(navigationForRoles(['auditor']).map(item => item.id)).toContain('sources')
    expect(navigationForRoles(['reviewer']).map(item => item.id)).not.toContain('sources')
    expect(navigationForRoles(['viewer']).map(item => item.id)).toEqual([])
  })

  it('removes legacy self-attestation and client-side lifecycle derivation', () => {
    const list = appSource('pages/admin/sources/index.vue')
    const detail = appSource('pages/admin/sources/[id].vue')
    const projection = appSource('source-center.ts')

    expect(list).toContain('useSourceCenterWorkspace')
    expect(list).toContain('SourceCandidateCard')
    expect(list).toContain('SourceCandidateDrawer')
    expect(list).not.toContain('filteredSources')
    expect(list).not.toContain("$fetch<SourceCenterDetail>('/api/v1/admin/sources'")
    expect(projection).toContain("source.lifecycle_state ?? 'UNKNOWN'")
    expect(projection).toContain("source.runtime_authorization ?? 'DENIED'")
    expect(projection).not.toContain("source.state === 'FIXTURE_TEST'")
    expect(projection).not.toContain("source.state === 'APPROVED'")
    expect(projection).not.toContain("source.state === 'ACTIVE'")
    expect(detail).toContain('available_actions')
    expect(detail).toContain('/policy-versions')
    expect(detail).toContain('/connector-config-versions/preview')
    expect(detail).toContain('/trial-runs')
    expect(detail).toContain('/complete-fixture')
    expect(detail).toContain('SourceFixtureTrialControls')
    expect(detail).toContain('/lifecycle-events')
    expect(detail).toContain('/audit-events')
    expect(detail).not.toContain('nextState')
    expect(detail).not.toContain('watchEffect')
    expect(detail).not.toContain('defaultExpiry')
    expect(detail).not.toContain('approval_id ||=')
    expect(detail).not.toContain('onboardingEvidence')
    expect(detail).not.toContain('/transitions')
    expect(detail).not.toContain('/enable')
    expect(detail).not.toContain('/disable')
    expect(detail).not.toContain('<textarea')
  })

  it('aligns the detail view to central governance contracts and never renders secrets', () => {
    const detail = appSource('pages/admin/sources/[id].vue')
    const projection = appSource('source-center.ts')

    expect(detail).toContain('/governance-metadata')
    expect(detail).toContain('/assessments')
    expect(detail).toContain('version.document.robots_review')
    expect(detail).toContain('version.document.terms_review')
    expect(detail).toContain('version.document.copyright_review')
    expect(detail).toContain('version.document.fetch')
    expect(detail).toContain('version.document.storage_policy')
    expect(detail).toContain('version.document.display_policy')
    expect(detail).toContain('version.document.download_policy')
    expect(detail).toContain('version.document.retention')
    expect(detail).toContain('version.document.legal_hold_policy')
    expect(detail).toContain('version.document.automatic_publication')
    expect(detail).toContain('version.document.slo')
    expect(detail).toContain('version.document.slo.authorization_confirmed')
    expect(detail).toContain('version.document.slo.technical_conditions_confirmed')
    expect(detail).toContain('name="slo-authorization-confirmed"')
    expect(detail).toContain('name="slo-technical-conditions-confirmed"')
    expect(detail).toContain('sourceSloPayload')
    expect(detail).toContain('connectorSaveReason')
    expect(detail).toContain('reason: connectorSaveReason.value.trim()')
    expect(detail).toContain('version.validation_status')
    expect(detail).toContain('safeConnectorConfigRows(version.config)')
    expect(detail).toContain('ready_ratio_bps')
    expect(detail).toContain('raw_count')
    expect(detail).toContain('ready_count')
    expect(detail).toContain('parse_failed_count')
    expect(detail).toContain('security_failed_count')
    expect(detail).toContain('rejected_raw_attempt_count')
    expect(detail).toContain('event.event_type')
    expect(detail).toContain('event.request_id')
    expect(detail).not.toContain('version.credential_alias')
    expect(detail).not.toContain('previewResult.config.credential_ref')
    expect(detail).not.toContain('event.summary')
    expect(detail).not.toContain('event.outcome')
    expect(projection).toContain('SourceCoverageCell as CanonicalSourceCoverageCell')
    expect(projection).toContain('SourceTrialQualitySummary as CanonicalSourceTrialQualitySummary')
    expect(projection).toContain('export type SourceCenterSummary = SourceSummary')
    expect(projection).toContain('export type SourceCenterDetail = SourceDetail')
    expect(projection).not.toContain('export interface SourceTrialQualitySummary')
    expect(projection).not.toContain("= | 'CANDIDATE'")
    expect(detail).not.toContain('trust_score')
    expect(detail).not.toContain('name="lifecycle')
  })

  it('publishes Round 15 lifecycle and connector types from generated contracts', () => {
    const generated = readFileSync(
      resolve(process.cwd(), '../../packages/contracts/generated/types/index.d.ts'),
      'utf8',
    )

    for (const exportedType of [
      'ConnectorType',
      'RuntimeAuthorization',
      'SourceAuthorityAssessment',
      'SourceCoverageCell',
      'SourceCoverageMatrix',
      'SourceIndependenceAssessment',
      'SourceLifecycleAction',
      'SourceLifecycleState',
      'SourceTrialKind',
      'SourceTrialQualitySummary',
      'SourceTrialRunStatus',
    ]) {
      expect(generated).toContain(`export type { ${exportedType} }`)
    }
  })
})
