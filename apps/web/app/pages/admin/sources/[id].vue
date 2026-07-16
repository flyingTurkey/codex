<script setup lang="ts">
import type { MeResponse } from '@srbg/contracts'
import { PageHeader, ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { computed, reactive, ref } from 'vue'

import ConnectorConfigEditor from '../../../components/ConnectorConfigEditor.vue'
import SourceFixtureTrialControls from '../../../components/SourceFixtureTrialControls.vue'
import SourceLifecycleControls from '../../../components/SourceLifecycleControls.vue'
import type {
  ConnectorConfigVersionView,
  ConnectorDefinitionView,
  ConnectorPreviewResult,
  DeclarativeConnectorPayload,
  SourceAuditEventView,
  SourceCenterDetail,
  SourceLifecycleAction,
  SourceLifecycleEventView,
  SourcePolicyVersionView,
  SourceTrialRunView,
} from '../../../source-center'
import {
  apiProblemMessage,
  formatShanghaiDateTime,
  lifecycleLabel,
  lifecycleStateOf,
  lifecycleTone,
  runtimeAuthorizationLabel,
  runtimeAuthorizationTone,
  safeConnectorConfigRows,
  shanghaiLocalDateTimeToUtc,
  sourceSloPayload,
} from '../../../source-center'

type DetailTab = 'overview' | 'policy' | 'connector' | 'trial' | 'audit'

const route = useRoute()
const sourceId = computed(() => String(route.params.id))
const activeTab = ref<DetailTab>('overview')
const busy = ref(false)
const actionError = ref<string | null>(null)
const policyOpen = ref(false)
const policyDecisionOpen = ref(false)
const connectorOpen = ref(false)
const trialOpen = ref(false)
const approvalOpen = ref(false)
const governanceMetadataOpen = ref(false)
const assessmentOpen = ref(false)
const selectedPolicyVersionId = ref('')
const previewResult = ref<ConnectorPreviewResult | null>(null)
const pendingConnectorConfig = ref<DeclarativeConnectorPayload | null>(null)
const connectorSaveReason = ref('')
const uploadedFixtureTrialIds = ref<string[]>([])

const tabs: readonly { id: DetailTab, label: string }[] = [
  { id: 'overview', label: '概览' },
  { id: 'policy', label: '策略版本' },
  { id: 'connector', label: '连接器配置' },
  { id: 'trial', label: '试运行' },
  { id: 'audit', label: '审计与状态事件' },
]

const { data: identity } = await useFetch<MeResponse>('/api/v1/me', {
  retry: 0,
  timeout: 2_000,
})
const canManage = computed(() => identity.value?.roles.some(role =>
  role === 'source_admin' || role === 'platform_admin',
) ?? false)

const {
  data: source,
  error,
  refresh: refreshSource,
} = await useFetch<SourceCenterDetail>(() => `/api/v1/admin/sources/${sourceId.value}`, {
  retry: 0,
  timeout: 5_000,
})

const {
  data: policyVersions,
  error: policyError,
  refresh: refreshPolicyVersions,
} = await useFetch<SourcePolicyVersionView[]>(
  () => `/api/v1/admin/sources/${sourceId.value}/policy-versions`,
  { default: () => [], retry: 0, timeout: 5_000 },
)

const {
  data: connectorVersions,
  error: connectorError,
  refresh: refreshConnectorVersions,
} = await useFetch<ConnectorConfigVersionView[]>(
  () => `/api/v1/admin/sources/${sourceId.value}/connector-config-versions`,
  { default: () => [], retry: 0, timeout: 5_000 },
)

const { data: connectorDefinitions } = await useFetch<ConnectorDefinitionView[]>(
  '/api/v1/admin/connector-definitions',
  { default: () => [], retry: 0, timeout: 5_000 },
)

const {
  data: trialRuns,
  error: trialError,
  refresh: refreshTrialRuns,
} = await useFetch<SourceTrialRunView[]>(
  () => `/api/v1/admin/sources/${sourceId.value}/trial-runs`,
  { default: () => [], retry: 0, timeout: 5_000 },
)

const {
  data: lifecycleEvents,
  error: lifecycleEventsError,
  refresh: refreshLifecycleEvents,
} = await useFetch<SourceLifecycleEventView[]>(
  () => `/api/v1/admin/sources/${sourceId.value}/lifecycle-events`,
  { default: () => [], retry: 0, timeout: 5_000 },
)

const {
  data: auditEvents,
  error: auditError,
  refresh: refreshAuditEvents,
} = await useFetch<SourceAuditEventView[]>(
  () => `/api/v1/admin/sources/${sourceId.value}/audit-events`,
  { default: () => [], retry: 0, timeout: 5_000 },
)

const lifecycleState = computed(() => source.value ? lifecycleStateOf(source.value) : 'UNKNOWN')
const availableActions = computed<readonly SourceLifecycleAction[]>(() =>
  source.value?.available_actions ?? [],
)
const connectorLabels = {
  DIRECT_PDF: 'PDF',
  JSON_API: 'JSON API',
  LIST_DETAIL: '列表 / 详情',
  MANUAL_IMPORT: '人工 URL / 文件导入',
  RSS_ATOM: 'RSS / Atom',
  SITEMAP: 'Sitemap',
} as const
const connectorDefinitionOptions = computed(() => connectorDefinitions.value.map(definition => ({
  connectorType: definition.connector_type,
  definitionVersion: definition.definition_version,
  label: connectorLabels[definition.connector_type],
})))

const industryOptions = [
  'HIGHWAY',
  'BRIDGE',
  'TUNNEL',
  'RAILWAY',
  'RAIL_TRANSIT',
  'GENERAL_TRANSPORT',
  'UNKNOWN',
] as const
const contentDomainOptions = [
  'DIGITAL_TRANSFORMATION_CASE',
  'RESEARCH_PAPER',
  'SOFTWARE_PLATFORM',
  'IOT_EQUIPMENT',
  'LOW_ALTITUDE_EQUIPMENT',
  'AI_APPLICATION',
  'SAFETY_REGULATION',
  'STANDARD_GUIDANCE',
  'ACCIDENT_INVESTIGATION',
  'OFFICIAL_NOTICE',
  'PENALTY',
  'RECTIFICATION',
  'UNKNOWN',
] as const
const declaredRoleOptions = [
  'OFFICIAL_PRIMARY',
  'OFFICIAL_SECONDARY',
  'STANDARDS_PUBLISHER',
  'RESEARCH_PUBLISHER',
  'MANUFACTURER',
  'INDEPENDENT_REPORTER',
  'AGGREGATOR',
  'UNKNOWN',
] as const
const authorityLevelOptions = ['A0', 'A1', 'B1', 'B2', 'C1', 'C2', 'UNKNOWN'] as const
const independenceLevelOptions = [
  'EDITORIALLY_INDEPENDENT',
  'PARTIALLY_INDEPENDENT',
  'NOT_INDEPENDENT',
  'UNKNOWN',
] as const

function hasAction(action: SourceLifecycleAction): boolean {
  return availableActions.value.includes(action)
}

const policy = reactive({
  allowedDomains: '',
  automaticPublication: '',
  copyrightCheckedAt: '',
  copyrightEvidenceSha256: '',
  copyrightEvidenceUrl: '',
  copyrightResult: '',
  deleteAfterRetention: '',
  displayPolicy: '',
  downloadPolicy: '',
  legalHoldPolicy: '',
  minimumIntervalSeconds: '' as '' | number,
  policyVersion: '',
  rateLimitPerMinute: '' as '' | number,
  reason: '',
  retentionDays: '' as '' | number,
  robotsCheckedAt: '',
  robotsEvidenceSha256: '',
  robotsEvidenceUrl: '',
  robotsResult: '',
  sloApplicability: '',
  sloAuthorizationConfirmed: false,
  sloReason: '',
  sloTargetMinutes: '' as '' | number,
  sloTechnicalConditionsConfirmed: false,
  storagePolicy: '',
  termsCheckedAt: '',
  termsEvidenceSha256: '',
  termsEvidenceUrl: '',
  termsResult: '',
  userAgent: '',
  validFrom: '',
  validUntil: '',
})

const policyDecision = reactive({ outcome: '', reason: '' })
const trialRequest = reactive({
  connectorConfigVersionId: '',
  kind: '' as '' | 'FIXTURE_REPLAY' | 'LIVE_TRIAL',
  policyVersionId: '',
  reason: '',
})
const productionApproval = reactive({
  connectorConfigVersionId: '',
  policyVersionId: '',
  reason: '',
  trialRunId: '',
})
const currentApprovedPolicies = computed(() => policyVersions.value.filter(version =>
  version.id === source.value?.current_policy_version_id && version.status === 'APPROVED',
))
const trialConnectorVersions = computed(() => connectorVersions.value.filter(version =>
  version.id === source.value?.current_connector_config_version_id
  && version.policy_version_id === trialRequest.policyVersionId
  && version.validation_status === 'VALID',
))
const approvalConnectorVersions = computed(() => connectorVersions.value.filter(version =>
  version.id === source.value?.current_connector_config_version_id
  && version.policy_version_id === productionApproval.policyVersionId
  && version.validation_status === 'VALID',
))
const approvalTrialRuns = computed(() => trialRuns.value.filter(run =>
  run.id === source.value?.current_trial_run_id
  && run.kind === 'LIVE_TRIAL'
  && run.status === 'SUCCEEDED'
  && run.policy_version_id === productionApproval.policyVersionId
  && run.connector_config_version_id === productionApproval.connectorConfigVersionId,
))
const governanceMetadata = reactive({
  contentDomains: [] as string[],
  countryCodes: '',
  declaredRoles: [] as string[],
  governanceOwnerId: '',
  industries: [] as string[],
  languageTags: '',
  reason: '',
  regionCodes: '',
})
const assessment = reactive({
  assessedAt: '',
  authorityEvidenceRefs: '',
  authorityLevel: '',
  authorityReasonCodes: '',
  authorityRuleVersion: '',
  independenceEvidenceRefs: '',
  independenceLevel: '',
  independenceReasonCodes: '',
  independenceRuleVersion: '',
  reason: '',
})
const policySloPayload = computed(() => sourceSloPayload({
  applicability: policy.sloApplicability,
  authorizationConfirmed: policy.sloAuthorizationConfirmed,
  reason: policy.sloReason,
  targetMinutes: policy.sloTargetMinutes,
  technicalConditionsConfirmed: policy.sloTechnicalConditionsConfirmed,
}))

function resetSourceSloConfirmations(): void {
  policy.sloAuthorizationConfirmed = false
  policy.sloTechnicalConditionsConfirmed = false
  if (policy.sloApplicability === 'APPLICABLE') policy.sloReason = ''
  if (policy.sloApplicability === 'NOT_APPLICABLE') policy.sloTargetMinutes = ''
}

function commaSeparatedValues(value: string): string[] {
  return [...new Set(value.split(',').map(item => item.trim()).filter(Boolean))]
}

function openGovernanceMetadata(): void {
  if (!source.value || !canManage.value) return
  governanceMetadata.governanceOwnerId = source.value.governance_owner_id ?? ''
  governanceMetadata.countryCodes = source.value.country_codes?.join(', ') ?? ''
  governanceMetadata.regionCodes = source.value.region_codes?.join(', ') ?? ''
  governanceMetadata.languageTags = source.value.language_tags?.join(', ') ?? ''
  governanceMetadata.industries = [...(source.value.industries ?? [])]
  governanceMetadata.contentDomains = [...(source.value.content_domains ?? [])]
  governanceMetadata.declaredRoles = [...(source.value.declared_roles ?? [])]
  governanceMetadata.reason = ''
  governanceMetadataOpen.value = true
}

function openAssessment(): void {
  if (!canManage.value) return
  assessment.assessedAt = ''
  assessment.authorityEvidenceRefs = ''
  assessment.authorityLevel = ''
  assessment.authorityReasonCodes = ''
  assessment.authorityRuleVersion = ''
  assessment.independenceEvidenceRefs = ''
  assessment.independenceLevel = ''
  assessment.independenceReasonCodes = ''
  assessment.independenceRuleVersion = ''
  assessment.reason = ''
  assessmentOpen.value = true
}

function openConnectorEditor(): void {
  if (!canManage.value) return
  connectorSaveReason.value = ''
  pendingConnectorConfig.value = null
  previewResult.value = null
  connectorOpen.value = true
}

function reviewPayload(
  result: string,
  evidenceUrl: string,
  evidenceSha256: string,
  checkedAt: string,
): Record<string, string> {
  return {
    checked_at: shanghaiLocalDateTimeToUtc(checkedAt),
    evidence_sha256: evidenceSha256,
    evidence_url: evidenceUrl,
    result,
  }
}

async function runMutation(action: () => Promise<unknown>, refreshes: readonly (() => Promise<unknown>)[]): Promise<boolean> {
  busy.value = true
  actionError.value = null
  try {
    await action()
    await Promise.all(refreshes.map(refresh => refresh()))
    return true
  } catch (requestError) {
    actionError.value = apiProblemMessage(requestError)
    return false
  } finally {
    busy.value = false
  }
}

async function submitGovernanceMetadata(): Promise<void> {
  if (!canManage.value) return
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/governance-metadata`, {
      body: {
        content_domains: governanceMetadata.contentDomains,
        country_codes: commaSeparatedValues(governanceMetadata.countryCodes),
        declared_roles: governanceMetadata.declaredRoles,
        governance_owner_id: governanceMetadata.governanceOwnerId,
        industries: governanceMetadata.industries,
        language_tags: commaSeparatedValues(governanceMetadata.languageTags),
        reason: governanceMetadata.reason,
        region_codes: commaSeparatedValues(governanceMetadata.regionCodes),
      },
      method: 'PUT',
      timeout: 5_000,
    }),
    [refreshSource, refreshAuditEvents],
  )
  if (succeeded) governanceMetadataOpen.value = false
}

async function submitAssessment(): Promise<void> {
  if (!canManage.value) return
  const assessedAt = shanghaiLocalDateTimeToUtc(assessment.assessedAt)
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/assessments`, {
      body: {
        authority: {
          assessed_at: assessedAt,
          evidence_refs: commaSeparatedValues(assessment.authorityEvidenceRefs),
          level: assessment.authorityLevel,
          reason_codes: commaSeparatedValues(assessment.authorityReasonCodes),
          rule_version: assessment.authorityRuleVersion,
        },
        independence: {
          assessed_at: assessedAt,
          evidence_refs: commaSeparatedValues(assessment.independenceEvidenceRefs),
          level: assessment.independenceLevel,
          reason_codes: commaSeparatedValues(assessment.independenceReasonCodes),
          rule_version: assessment.independenceRuleVersion,
        },
        reason: assessment.reason,
      },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshSource, refreshAuditEvents],
  )
  if (succeeded) assessmentOpen.value = false
}

async function executeLifecycleCommand(payload: { action: SourceLifecycleAction, reason: string }): Promise<void> {
  const endpoints: Partial<Record<SourceLifecycleAction, string>> = {
    PAUSE: 'pause',
    RESUME: 'resume',
    RETIRE: 'retire',
    SUBMIT_COMPLIANCE: 'submit-compliance',
  }
  const endpoint = endpoints[payload.action]
  if (!endpoint || !hasAction(payload.action)) {
    actionError.value = '服务端未提供此生命周期操作。'
    return
  }
  await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/${endpoint}`, {
      body: { reason: payload.reason },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshSource, refreshLifecycleEvents, refreshAuditEvents],
  )
}

async function submitPolicy(): Promise<void> {
  const slo = policySloPayload.value
  if (!slo) {
    actionError.value = '来源 SLO 必须明确适用性；适用时需同时确认授权和技术条件。'
    return
  }
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/policy-versions`, {
      body: {
        automatic_publication: policy.automaticPublication,
        copyright_review: reviewPayload(
          policy.copyrightResult,
          policy.copyrightEvidenceUrl,
          policy.copyrightEvidenceSha256,
          policy.copyrightCheckedAt,
        ),
        display_policy: policy.displayPolicy,
        download_policy: policy.downloadPolicy,
        fetch: {
          allowed_domains: policy.allowedDomains.split(',').map(value => value.trim()).filter(Boolean),
          minimum_interval_seconds: policy.minimumIntervalSeconds,
          rate_limit_per_minute: policy.rateLimitPerMinute,
          user_agent: policy.userAgent,
        },
        legal_hold_policy: policy.legalHoldPolicy,
        policy_version: policy.policyVersion,
        reason: policy.reason,
        retention: {
          delete_after_retention: policy.deleteAfterRetention === 'true',
          retention_days: policy.retentionDays,
        },
        robots_review: reviewPayload(
          policy.robotsResult,
          policy.robotsEvidenceUrl,
          policy.robotsEvidenceSha256,
          policy.robotsCheckedAt,
        ),
        schema_version: '2.0.0',
        slo,
        storage_policy: policy.storagePolicy,
        terms_review: reviewPayload(
          policy.termsResult,
          policy.termsEvidenceUrl,
          policy.termsEvidenceSha256,
          policy.termsCheckedAt,
        ),
        valid_from: shanghaiLocalDateTimeToUtc(policy.validFrom),
        valid_until: shanghaiLocalDateTimeToUtc(policy.validUntil),
      },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshPolicyVersions, refreshAuditEvents, refreshSource],
  )
  if (succeeded) policyOpen.value = false
}

function openPolicyDecision(policyVersionId: string): void {
  selectedPolicyVersionId.value = policyVersionId
  policyDecision.outcome = ''
  policyDecision.reason = ''
  policyDecisionOpen.value = true
}

async function submitPolicyDecision(): Promise<void> {
  if (!selectedPolicyVersionId.value) return
  const succeeded = await runMutation(
    () => $fetch(
      `/api/v1/admin/sources/${sourceId.value}/policy-versions/${selectedPolicyVersionId.value}/decisions`,
      {
        body: { outcome: policyDecision.outcome, reason: policyDecision.reason },
        method: 'POST',
        timeout: 5_000,
      },
    ),
    [refreshPolicyVersions, refreshAuditEvents, refreshSource],
  )
  if (succeeded) policyDecisionOpen.value = false
}

async function previewConnector(payload: DeclarativeConnectorPayload): Promise<void> {
  busy.value = true
  actionError.value = null
  previewResult.value = null
  try {
    previewResult.value = await $fetch<ConnectorPreviewResult>(
      `/api/v1/admin/sources/${sourceId.value}/connector-config-versions/preview`,
      { body: payload, method: 'POST', timeout: 5_000 },
    )
    pendingConnectorConfig.value = payload
    connectorSaveReason.value = ''
    await refreshAuditEvents()
  } catch (requestError) {
    pendingConnectorConfig.value = null
    actionError.value = apiProblemMessage(requestError)
  } finally {
    busy.value = false
  }
}

async function saveConnectorVersion(): Promise<void> {
  if (!pendingConnectorConfig.value || !previewResult.value || !connectorSaveReason.value.trim()) return
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/connector-config-versions`, {
      body: {
        ...pendingConnectorConfig.value,
        reason: connectorSaveReason.value.trim(),
      },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshConnectorVersions, refreshAuditEvents, refreshSource],
  )
  if (succeeded) {
    connectorOpen.value = false
    pendingConnectorConfig.value = null
    previewResult.value = null
    connectorSaveReason.value = ''
  }
}

async function submitTrialRequest(): Promise<void> {
  const requiredAction: SourceLifecycleAction
    = trialRequest.kind === 'LIVE_TRIAL' ? 'START_LIVE_TRIAL' : 'START_FIXTURE_TRIAL'
  if (!hasAction(requiredAction)) {
    actionError.value = '服务端未授权此类试运行。'
    return
  }
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/trial-runs`, {
      body: {
        connector_config_version_id: trialRequest.connectorConfigVersionId,
        kind: trialRequest.kind,
        policy_version_id: trialRequest.policyVersionId,
        reason: trialRequest.reason,
      },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshTrialRuns, refreshLifecycleEvents, refreshAuditEvents, refreshSource],
  )
  if (succeeded) trialOpen.value = false
}

async function uploadFixture(
  trialId: string,
  payload: { canonicalUrl: string, file: File },
): Promise<void> {
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/fixture`, {
      body: payload.file,
      headers: {
        'Content-Type': payload.file.type || 'application/octet-stream',
        'X-Document-URL': payload.canonicalUrl,
        'X-Filename': payload.file.name,
      },
      method: 'POST',
      timeout: 15_000,
    }),
    [refreshAuditEvents],
  )
  if (succeeded && !uploadedFixtureTrialIds.value.includes(trialId)) {
    uploadedFixtureTrialIds.value = [...uploadedFixtureTrialIds.value, trialId]
  }
}

async function completeFixture(
  trialId: string,
  payload: { reason: string },
): Promise<void> {
  const succeeded = await runMutation(
    () => $fetch(
      `/api/v1/admin/sources/${sourceId.value}/trial-runs/${trialId}/complete-fixture`,
      {
        body: { reason: payload.reason },
        method: 'POST',
        timeout: 15_000,
      },
    ),
    [refreshTrialRuns, refreshSource, refreshLifecycleEvents, refreshAuditEvents],
  )
  if (succeeded) {
    uploadedFixtureTrialIds.value = uploadedFixtureTrialIds.value.filter(id => id !== trialId)
  }
}

function openTrialRequest(): void {
  trialRequest.policyVersionId = source.value?.current_policy_version_id ?? ''
  trialRequest.connectorConfigVersionId
    = source.value?.current_connector_config_version_id ?? ''
  trialRequest.kind = ''
  trialRequest.reason = ''
  trialOpen.value = true
}

async function submitProductionApproval(): Promise<void> {
  if (!hasAction('APPROVE_PRODUCTION')) {
    actionError.value = '服务端未提供生产批准操作。'
    return
  }
  const succeeded = await runMutation(
    () => $fetch(`/api/v1/admin/sources/${sourceId.value}/approve`, {
      body: {
        connector_config_version_id: productionApproval.connectorConfigVersionId,
        policy_version_id: productionApproval.policyVersionId,
        reason: productionApproval.reason,
        trial_run_id: productionApproval.trialRunId,
      },
      method: 'POST',
      timeout: 5_000,
    }),
    [refreshSource, refreshLifecycleEvents, refreshAuditEvents],
  )
  if (succeeded) approvalOpen.value = false
}

function openProductionApproval(): void {
  productionApproval.policyVersionId = source.value?.current_policy_version_id ?? ''
  productionApproval.connectorConfigVersionId
    = source.value?.current_connector_config_version_id ?? ''
  productionApproval.trialRunId = source.value?.current_trial_run_id ?? ''
  productionApproval.reason = ''
  approvalOpen.value = true
}

function trialKind(run: SourceTrialRunView): 'FIXTURE_REPLAY' | 'LIVE_TRIAL' {
  return run.kind
}

function trialReadyRatio(run: SourceTrialRunView): string {
  const basisPoints = run.quality_summary?.ready_ratio_bps
  return basisPoints === undefined ? '待评估' : `${(basisPoints / 100).toFixed(2)}% READY`
}

function isCurrentPendingFixture(run: SourceTrialRunView): boolean {
  return canManage.value
    && run.kind === 'FIXTURE_REPLAY'
    && run.status === 'PENDING'
    && run.id === source.value?.current_trial_run_id
}
</script>

<template>
  <section v-if="source" class="source-detail-page">
    <PageHeader
      :title="source.name"
      eyebrow="来源中心 V2"
      :description="source.base_url"
      :updated-at="source.created_at"
      updated-label="登记时间"
    >
      <template #status>
        <StatusBadge :tone="lifecycleTone(source)" :label="lifecycleLabel(source)" />
        <StatusBadge
          :tone="runtimeAuthorizationTone(source)"
          :label="runtimeAuthorizationLabel(source)"
        />
        <span>配置、审批与状态均以服务端事实为准</span>
      </template>
      <template #actions>
        <SourceLifecycleControls
          v-if="canManage"
          :available-actions="availableActions"
          :busy="busy"
          :lifecycle-state="lifecycleState"
          @command="executeLifecycleCommand"
        />
        <button
          v-if="canManage && hasAction('APPROVE_PRODUCTION')"
          class="primary-button"
          type="button"
          :disabled="busy"
          @click="openProductionApproval"
        >
          批准生产
        </button>
      </template>
    </PageHeader>

    <p v-if="!canManage" class="read-only-note" role="note">
      只读审计视图：可以查看策略、试运行、状态事件和脱敏配置，不能发起治理写操作。
    </p>
    <p v-if="actionError" class="problem" role="alert">{{ actionError }}</p>

    <div class="detail-tabs" role="tablist" aria-label="来源治理档案">
      <button
        v-for="tab in tabs"
        :id="`source-tab-${tab.id}`"
        :key="tab.id"
        class="tab-button"
        type="button"
        role="tab"
        :aria-controls="`source-panel-${tab.id}`"
        :aria-selected="activeTab === tab.id"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <section
      v-if="activeTab === 'overview'"
      id="source-panel-overview"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="source-tab-overview"
    >
      <div class="detail-grid">
        <article class="panel">
          <h2>权威运行授权</h2>
          <dl class="metadata-list">
            <div><dt>运行授权</dt><dd>{{ source.runtime_authorization ?? 'DENIED' }}</dd></div>
            <div><dt>V2 生命周期</dt><dd>{{ lifecycleState }}</dd></div>
            <div><dt>当前策略版本</dt><dd>{{ source.current_policy_version_id ?? '缺失' }}</dd></div>
            <div><dt>当前配置版本</dt><dd>{{ source.current_connector_config_version_id ?? '缺失' }}</dd></div>
            <div><dt>当前试运行</dt><dd>{{ source.current_trial_run_id ?? '缺失' }}</dd></div>
          </dl>
          <p class="field-note">生产资格只由服务端根据当前同版本的策略、最新合规决定、连接器配置、真实试运行、人工审批和职责分离计算；Fixture 永不授予生产授权。</p>
          <details class="compatibility-details">
            <summary>V1 准入兼容投影（只读）</summary>
            <dl class="metadata-list">
              <div><dt>旧策略</dt><dd>{{ source.eligibility.policy_valid ? '有效' : '缺失 / 过期' }}</dd></div>
              <div><dt>旧 onboarding</dt><dd>{{ source.eligibility.onboarding_valid ? '有效' : '缺失 / 过期' }}</dd></div>
              <div><dt>旧策略匹配</dt><dd>{{ source.eligibility.onboarding_policy_matches ? '匹配' : '不匹配' }}</dd></div>
              <div><dt>历史 Fixture</dt><dd>{{ source.eligibility.fixture_count }}</dd></div>
            </dl>
          </details>
          <ul v-if="source.eligibility.missing_reasons.length" class="missing-list" aria-label="V1 兼容准入缺失原因">
            <li v-for="reason in source.eligibility.missing_reasons" :key="reason">{{ reason }}</li>
          </ul>
        </article>

        <article class="panel">
          <div class="version-card__title">
            <h2>治理与覆盖维度</h2>
            <button v-if="canManage" class="text-button" type="button" @click="openGovernanceMetadata">更新治理元数据</button>
          </div>
          <dl class="metadata-list">
            <div><dt>治理责任人</dt><dd>{{ source.governance_owner_id ?? 'UNKNOWN' }}</dd></div>
            <div><dt>工程行业</dt><dd>{{ source.industries?.join(' / ') || 'UNKNOWN' }}</dd></div>
            <div><dt>内容域</dt><dd>{{ source.content_domains?.join(' / ') || 'UNKNOWN' }}</dd></div>
            <div><dt>国家 / 地区</dt><dd>{{ source.country_codes?.join(' / ') || 'UNKNOWN' }} · {{ source.region_codes?.join(' / ') || 'UNKNOWN' }}</dd></div>
            <div><dt>语言</dt><dd>{{ source.language_tags?.join(' / ') || 'UNKNOWN' }}</dd></div>
            <div><dt>来源声明角色</dt><dd>{{ source.declared_roles?.join(' / ') || 'UNKNOWN' }}</dd></div>
          </dl>
          <p class="field-note">来源声明角色只描述来源身份，不能替代具体事实的证据。</p>
        </article>

        <article class="panel">
          <div class="version-card__title">
            <h2>来源权威</h2>
            <button v-if="canManage" class="text-button" type="button" @click="openAssessment">追加双维评估</button>
          </div>
          <dl class="metadata-list">
            <div><dt>等级</dt><dd>{{ source.source_authority?.level ?? 'UNKNOWN' }}</dd></div>
            <div><dt>规则版本</dt><dd>{{ source.source_authority?.rule_version ?? '未评估' }}</dd></div>
            <div><dt>理由代码</dt><dd>{{ source.source_authority?.reason_codes?.join(' / ') || '—' }}</dd></div>
          </dl>
        </article>

        <article class="panel">
          <h2>来源独立性</h2>
          <dl class="metadata-list">
            <div><dt>等级</dt><dd>{{ source.source_independence?.level ?? 'UNKNOWN' }}</dd></div>
            <div><dt>规则版本</dt><dd>{{ source.source_independence?.rule_version ?? '未评估' }}</dd></div>
            <div><dt>理由代码</dt><dd>{{ source.source_independence?.reason_codes?.join(' / ') || '—' }}</dd></div>
          </dl>
        </article>
      </div>
    </section>

    <section
      v-if="activeTab === 'policy'"
      id="source-panel-policy"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="source-tab-policy"
    >
      <div class="section-heading">
        <div><h2>策略版本</h2><p>版本只追加不覆盖；策略提交与人工决定分别留痕。</p></div>
        <button v-if="canManage" class="primary-button" type="button" @click="policyOpen = true">新建策略版本</button>
      </div>
      <p v-if="policyError" class="problem" role="alert">策略版本不可用；未用旧策略替代。</p>
      <div v-else class="version-cards policy-version-cards" aria-label="策略版本列表">
        <article v-for="version in policyVersions" :key="version.id" class="version-card policy-card">
          <div class="version-card__title">
            <h3>{{ version.policy_version }} · Schema {{ version.schema_version }}</h3>
            <StatusBadge :tone="version.status === 'VALID' ? 'healthy' : 'pending'" :label="version.status" />
          </div>
          <dl class="metadata-list">
            <div><dt>有效期</dt><dd>{{ formatShanghaiDateTime(version.valid_from) }} → {{ formatShanghaiDateTime(version.valid_until) }}</dd></div>
            <div><dt>文档哈希</dt><dd>{{ version.document_sha256 }}</dd></div>
            <div><dt>提交时间</dt><dd>{{ formatShanghaiDateTime(version.created_at) }}</dd></div>
          </dl>
          <div class="policy-evidence-grid">
            <section>
              <h4>robots 证据</h4>
              <dl class="metadata-list">
                <div><dt>结论</dt><dd>{{ version.document.robots_review.result }}</dd></div>
                <div><dt>SHA-256</dt><dd>{{ version.document.robots_review.evidence_sha256 ?? '缺失' }}</dd></div>
                <div><dt>证据 URL</dt><dd>{{ version.document.robots_review.evidence_url }}</dd></div>
                <div><dt>检查时间</dt><dd>{{ formatShanghaiDateTime(version.document.robots_review.checked_at) }}</dd></div>
              </dl>
            </section>
            <section>
              <h4>条款证据</h4>
              <dl class="metadata-list">
                <div><dt>结论</dt><dd>{{ version.document.terms_review.result }}</dd></div>
                <div><dt>SHA-256</dt><dd>{{ version.document.terms_review.evidence_sha256 ?? '缺失' }}</dd></div>
                <div><dt>证据 URL</dt><dd>{{ version.document.terms_review.evidence_url }}</dd></div>
                <div><dt>检查时间</dt><dd>{{ formatShanghaiDateTime(version.document.terms_review.checked_at) }}</dd></div>
              </dl>
            </section>
            <section>
              <h4>版权证据</h4>
              <dl class="metadata-list">
                <div><dt>结论</dt><dd>{{ version.document.copyright_review.result }}</dd></div>
                <div><dt>SHA-256</dt><dd>{{ version.document.copyright_review.evidence_sha256 ?? '缺失' }}</dd></div>
                <div><dt>证据 URL</dt><dd>{{ version.document.copyright_review.evidence_url }}</dd></div>
                <div><dt>检查时间</dt><dd>{{ formatShanghaiDateTime(version.document.copyright_review.checked_at) }}</dd></div>
              </dl>
            </section>
          </div>
          <dl class="metadata-list policy-controls">
            <div><dt>抓取</dt><dd>{{ version.document.fetch.allowed_domains.join(' / ') }} · 最小间隔 {{ version.document.fetch.minimum_interval_seconds }} 秒 · {{ version.document.fetch.rate_limit_per_minute }}/分钟 · {{ version.document.fetch.user_agent }}</dd></div>
            <div><dt>存储</dt><dd>{{ version.document.storage_policy }}</dd></div>
            <div><dt>展示</dt><dd>{{ version.document.display_policy }}</dd></div>
            <div><dt>下载</dt><dd>{{ version.document.download_policy }}</dd></div>
            <div><dt>保留</dt><dd>{{ version.document.retention.retention_days }} 天 · {{ version.document.retention.delete_after_retention ? '到期删除' : '到期不自动删除' }}</dd></div>
            <div><dt>法律保全</dt><dd>{{ version.document.legal_hold_policy }}</dd></div>
            <div><dt>自动发布</dt><dd>{{ version.document.automatic_publication }}</dd></div>
            <div><dt>来源 SLO</dt><dd>{{ version.document.slo.applicability }} · {{ version.document.slo.target_minutes ? `${version.document.slo.target_minutes} 分钟` : version.document.slo.reason ?? '未说明' }}</dd></div>
            <div><dt>SLO 条件复核</dt><dd>{{ version.document.slo.authorization_confirmed ? '授权已确认' : '授权未确认' }} · {{ version.document.slo.technical_conditions_confirmed ? '技术条件已确认' : '技术条件未确认' }}</dd></div>
          </dl>
          <button v-if="canManage" class="text-button policy-decision-button" type="button" @click="openPolicyDecision(version.id)">记录人工决定</button>
        </article>
        <p v-if="policyVersions.length === 0" class="empty-copy">尚无策略版本；生产授权保持拒绝。</p>
      </div>
    </section>

    <section
      v-if="activeTab === 'connector'"
      id="source-panel-connector"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="source-tab-connector"
    >
      <div class="section-heading">
        <div><h2>声明式连接器配置</h2><p>只显示服务端脱敏后的规范化字段与凭据是否存在；绝不回显密钥引用或明文。</p></div>
        <button v-if="canManage" class="primary-button" type="button" @click="openConnectorEditor">新建连接器配置</button>
      </div>
      <p v-if="connectorError" class="problem" role="alert">连接器配置不可用。</p>
      <div v-else class="version-cards">
        <article v-for="version in connectorVersions" :key="version.id" class="version-card">
          <div class="version-card__title"><h3>{{ version.connector_type }} · v{{ version.version_number }}</h3><StatusBadge :tone="version.validation_status === 'VALID' ? 'healthy' : 'conflict'" :label="version.validation_status" /></div>
          <dl class="metadata-list">
            <div><dt>Definition</dt><dd>{{ version.definition_version }}</dd></div>
            <div><dt>绑定策略</dt><dd>{{ version.policy_version_id }}</dd></div>
            <div><dt>配置哈希</dt><dd>{{ version.config_sha256 }}</dd></div>
            <div><dt>允许主机</dt><dd>{{ version.allowed_hosts.join(' / ') }}</dd></div>
            <div><dt>凭据</dt><dd>{{ version.credential_configured ? '已配置（引用不显示）' : '未配置' }}</dd></div>
            <div v-for="row in safeConnectorConfigRows(version.config)" :key="row.label"><dt>配置 · {{ row.label }}</dt><dd>{{ row.value }}</dd></div>
            <div><dt>创建时间</dt><dd>{{ formatShanghaiDateTime(version.created_at) }}</dd></div>
          </dl>
        </article>
        <p v-if="connectorVersions.length === 0" class="empty-copy">尚无连接器配置版本。</p>
      </div>
    </section>

    <section
      v-if="activeTab === 'trial'"
      id="source-panel-trial"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="source-tab-trial"
    >
      <div class="section-heading">
        <div><h2>试运行</h2><p>Fixture 与真实试运行分别授权、分别留证，且与生产数据隔离。</p></div>
        <button
          v-if="canManage && (hasAction('START_FIXTURE_TRIAL') || hasAction('START_LIVE_TRIAL'))"
          class="primary-button"
          type="button"
          @click="openTrialRequest"
        >
          申请试运行
        </button>
      </div>
      <p class="isolation-note" role="note"><strong>与生产数据隔离</strong>：试运行不会写入生产 DocumentVersion；激活后必须重新形成生产采集证据。</p>
      <p v-if="trialError" class="problem" role="alert">试运行记录不可用。</p>
      <div v-else class="version-cards">
        <article v-for="run in trialRuns" :key="run.id" class="version-card">
          <div class="version-card__title">
            <h3>{{ trialKind(run) === 'FIXTURE_REPLAY' ? 'Fixture 回放' : trialKind(run) === 'LIVE_TRIAL' ? '真实试运行' : '权威类型不可用' }}</h3>
            <StatusBadge :tone="run.status === 'SUCCEEDED' ? 'healthy' : 'pending'" :label="run.status" />
          </div>
          <dl class="metadata-list">
            <div><dt>隔离域</dt><dd>{{ trialKind(run) === 'FIXTURE_REPLAY' ? 'FIXTURE' : trialKind(run) === 'LIVE_TRIAL' ? 'TRIAL' : 'UNKNOWN' }}</dd></div>
            <div><dt>质量</dt><dd>{{ trialReadyRatio(run) }}</dd></div>
            <div><dt>Raw / READY</dt><dd>{{ run.quality_summary ? `${run.quality_summary.raw_count} / ${run.quality_summary.ready_count}` : '—' }}</dd></div>
            <div><dt>解析 / 安全失败</dt><dd>{{ run.quality_summary ? `${run.quality_summary.parse_failed_count} / ${run.quality_summary.security_failed_count}` : '—' }}</dd></div>
            <div><dt>拒绝的原始尝试</dt><dd>{{ run.quality_summary ? run.quality_summary.rejected_raw_attempt_count : '—' }}</dd></div>
            <div><dt>绑定策略 / 配置</dt><dd>{{ run.policy_version_id }} / {{ run.connector_config_version_id }}</dd></div>
            <div><dt>开始时间</dt><dd>{{ formatShanghaiDateTime(run.started_at ?? run.created_at) }}</dd></div>
          </dl>
          <SourceFixtureTrialControls
            v-if="isCurrentPendingFixture(run)"
            :busy="busy"
            :uploaded="uploadedFixtureTrialIds.includes(run.id)"
            @upload="payload => uploadFixture(run.id, payload)"
            @complete="payload => completeFixture(run.id, payload)"
          />
        </article>
        <p v-if="trialRuns.length === 0" class="empty-copy">尚无试运行记录；Fixture 不产生生产授权。</p>
      </div>
    </section>

    <section
      v-if="activeTab === 'audit'"
      id="source-panel-audit"
      class="tab-panel"
      role="tabpanel"
      aria-labelledby="source-tab-audit"
    >
      <div class="audit-grid">
        <article class="panel">
          <h2>状态事件</h2>
          <p v-if="lifecycleEventsError" class="problem" role="alert">状态事件不可用；历史没有被省略替代。</p>
          <ol v-else class="event-list">
            <li v-for="event in lifecycleEvents" :key="event.id">
              <div><strong>{{ event.action ?? event.reason_code ?? event.to_state }}</strong><time :datetime="event.created_at">{{ formatShanghaiDateTime(event.created_at) }}</time></div>
              <p>{{ event.from_state ?? '—' }} → {{ event.to_state }} · {{ event.reason }}</p>
              <span>actor: {{ event.actor_id ?? 'SYSTEM' }}</span>
            </li>
            <li v-if="lifecycleEvents.length === 0">尚无状态事件。</li>
          </ol>
        </article>
        <article class="panel">
          <h2>治理审计</h2>
          <p v-if="auditError" class="problem" role="alert">审计记录不可用或当前角色无权读取。</p>
          <ol v-else class="event-list">
            <li v-for="event in auditEvents" :key="event.id">
              <div><strong>{{ event.event_type }}</strong><time :datetime="event.created_at">{{ formatShanghaiDateTime(event.created_at) }}</time></div>
              <p>{{ event.reason }}</p>
              <span>request: {{ event.request_id }} · actor: {{ event.actor_id }}</span>
            </li>
            <li v-if="auditEvents.length === 0">尚无审计记录。</li>
          </ol>
        </article>
      </div>
    </section>

    <ResponsiveDrawer v-model="governanceMetadataOpen" title="更新治理元数据" description="只更新责任人与覆盖分类；生命周期和生产授权仍由服务端命令计算。">
      <form id="governance-metadata-form" class="drawer-form" @submit.prevent="submitGovernanceMetadata">
        <label>治理责任人 ID<input v-model.trim="governanceMetadata.governanceOwnerId" name="governance-owner-id" required pattern="[0-9a-fA-F-]{36}" maxlength="36"></label>
        <label>国家代码（逗号分隔）<input v-model.trim="governanceMetadata.countryCodes" name="country-codes" required maxlength="200" placeholder="CN"></label>
        <label>地区代码（逗号分隔）<input v-model.trim="governanceMetadata.regionCodes" name="region-codes" required maxlength="500" placeholder="CN-SC"></label>
        <label>语言标签（逗号分隔）<input v-model.trim="governanceMetadata.languageTags" name="language-tags" required maxlength="200" placeholder="zh-CN"></label>
        <label>工程行业（可多选）<select v-model="governanceMetadata.industries" name="industries" required multiple size="7"><option v-for="option in industryOptions" :key="option" :value="option">{{ option }}</option></select></label>
        <label>内容域（可多选）<select v-model="governanceMetadata.contentDomains" name="content-domains" required multiple size="8"><option v-for="option in contentDomainOptions" :key="option" :value="option">{{ option }}</option></select></label>
        <label>来源声明角色（可多选）<select v-model="governanceMetadata.declaredRoles" name="declared-roles" required multiple size="8"><option v-for="option in declaredRoleOptions" :key="option" :value="option">{{ option }}</option></select></label>
        <label>更新原因<input v-model.trim="governanceMetadata.reason" name="governance-metadata-reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="governanceMetadataOpen = false">取消</button><button class="primary-button" type="submit" form="governance-metadata-form" :disabled="busy">保存治理元数据</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="assessmentOpen" title="追加来源双维评估" description="权威与独立性分别解释、一起追加留痕；它们不替代具体事实证据，也不会合成为信任分。">
      <form id="source-assessment-form" class="drawer-form" @submit.prevent="submitAssessment">
        <label>评估时间<input v-model="assessment.assessedAt" name="assessment-time" required type="datetime-local"></label>
        <fieldset>
          <legend>来源权威</legend>
          <label>权威等级<select v-model="assessment.authorityLevel" name="authority-level" required><option value="" disabled>请选择</option><option v-for="option in authorityLevelOptions" :key="option" :value="option">{{ option }}</option></select></label>
          <label>权威规则版本<input v-model.trim="assessment.authorityRuleVersion" name="authority-rule-version" required maxlength="50"></label>
          <label>权威理由代码（逗号分隔）<input v-model.trim="assessment.authorityReasonCodes" name="authority-reason-codes" required maxlength="1000"></label>
          <label>权威证据引用（逗号分隔）<input v-model.trim="assessment.authorityEvidenceRefs" name="authority-evidence-refs" maxlength="4000"></label>
        </fieldset>
        <fieldset>
          <legend>来源独立性</legend>
          <label>独立性等级<select v-model="assessment.independenceLevel" name="independence-level" required><option value="" disabled>请选择</option><option v-for="option in independenceLevelOptions" :key="option" :value="option">{{ option }}</option></select></label>
          <label>独立性规则版本<input v-model.trim="assessment.independenceRuleVersion" name="independence-rule-version" required maxlength="50"></label>
          <label>独立性理由代码（逗号分隔）<input v-model.trim="assessment.independenceReasonCodes" name="independence-reason-codes" required maxlength="1000"></label>
          <label>独立性证据引用（逗号分隔）<input v-model.trim="assessment.independenceEvidenceRefs" name="independence-evidence-refs" maxlength="4000"></label>
        </fieldset>
        <label>追加原因<input v-model.trim="assessment.reason" name="assessment-reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="assessmentOpen = false">取消</button><button class="primary-button" type="submit" form="source-assessment-form" :disabled="busy">追加评估</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="policyOpen" title="新建策略版本" description="提交策略不会自动批准；审批人必须满足职责分离，决定由服务端另行记录。">
      <form id="policy-version-form" class="drawer-form" @submit.prevent="submitPolicy">
        <p class="form-note" role="note"><strong>提交策略不会自动批准。</strong> robots、条款、版权或任何治理字段不明确时必须选择非允许结论，服务端将默认拒绝。</p>
        <label>策略版本<input v-model.trim="policy.policyVersion" required maxlength="50" placeholder="2.0.0"></label>
        <div class="field-grid"><label>有效期开始<input v-model="policy.validFrom" required type="datetime-local"></label><label>有效期结束<input v-model="policy.validUntil" required type="datetime-local"></label></div>
        <fieldset><legend>robots 证据</legend><label>robots 结论<select v-model="policy.robotsResult" required><option value="" disabled>请选择</option><option value="ALLOWED">明确允许</option><option value="RESTRICTED">受限</option><option value="NOT_PRESENT">未找到</option><option value="BLOCKED">禁止</option></select></label><label>robots 证据 URL<input v-model.trim="policy.robotsEvidenceUrl" required type="url"></label><label>robots 证据 SHA-256<input v-model.trim="policy.robotsEvidenceSha256" required pattern="[a-f0-9]{64}" maxlength="64"></label><label>robots 检查时间<input v-model="policy.robotsCheckedAt" required type="datetime-local"></label></fieldset>
        <fieldset><legend>条款证据</legend><label>条款结论<select v-model="policy.termsResult" required><option value="" disabled>请选择</option><option value="ALLOWED">明确允许</option><option value="RESTRICTED">受限</option><option value="NOT_PRESENT">未找到</option><option value="BLOCKED">禁止</option></select></label><label>条款证据 URL<input v-model.trim="policy.termsEvidenceUrl" required type="url"></label><label>条款证据 SHA-256<input v-model.trim="policy.termsEvidenceSha256" required pattern="[a-f0-9]{64}" maxlength="64"></label><label>条款检查时间<input v-model="policy.termsCheckedAt" required type="datetime-local"></label></fieldset>
        <fieldset><legend>版权证据</legend><label>版权结论<select v-model="policy.copyrightResult" required><option value="" disabled>请选择</option><option value="ALLOWED">明确允许</option><option value="RESTRICTED">受限</option><option value="NOT_PRESENT">未找到</option><option value="BLOCKED">禁止</option></select></label><label>版权证据 URL<input v-model.trim="policy.copyrightEvidenceUrl" required type="url"></label><label>版权证据 SHA-256<input v-model.trim="policy.copyrightEvidenceSha256" required pattern="[a-f0-9]{64}" maxlength="64"></label><label>版权检查时间<input v-model="policy.copyrightCheckedAt" required type="datetime-local"></label></fieldset>
        <label>允许域名（逗号分隔）<input v-model.trim="policy.allowedDomains" required maxlength="1000"></label>
        <div class="field-grid"><label>最小访问间隔（秒）<input v-model.number="policy.minimumIntervalSeconds" required type="number" min="1"></label><label>每分钟访问上限<input v-model.number="policy.rateLimitPerMinute" required type="number" min="1"></label></div>
        <label>User-Agent<input v-model.trim="policy.userAgent" required maxlength="300"></label>
        <div class="field-grid"><label>存储策略<select v-model="policy.storagePolicy" required><option value="" disabled>请选择</option><option value="RAW_EVIDENCE_ALLOWED">允许保存原始证据</option><option value="METADATA_ONLY">仅元数据</option><option value="LINK_ONLY">仅链接</option></select></label><label>展示策略<select v-model="policy.displayPolicy" required><option value="" disabled>请选择</option><option value="METADATA_EXCERPT_LINK">题录 / 摘要 / 链接</option><option value="OFFICIAL_READER_LINK">官方阅读器链接</option><option value="LINK_ONLY">仅链接</option></select></label></div>
        <div class="field-grid"><label>下载策略<select v-model="policy.downloadPolicy" required><option value="" disabled>请选择</option><option value="DISABLED">禁止下载</option><option value="ORIGINAL_LINK_ONLY">仅原文链接</option><option value="SIGNED_INTERNAL_COPY">内部签名副本</option></select></label><label>法律保全<select v-model="policy.legalHoldPolicy" required><option value="" disabled>请选择</option><option value="SUPPORTED">支持</option><option value="NOT_APPLICABLE">不适用</option></select></label></div>
        <div class="field-grid"><label>保留天数<input v-model.number="policy.retentionDays" required type="number" min="1" max="36500"></label><label>到期删除<select v-model="policy.deleteAfterRetention" required><option value="" disabled>请选择</option><option value="true">是</option><option value="false">否</option></select></label></div>
        <label>自动发布策略<select v-model="policy.automaticPublication" required><option value="" disabled>请选择</option><option value="DISABLED">禁用</option><option value="PUBLICATION_GATE_ELIGIBLE">仅可进入发布门禁</option></select></label>
        <label>来源 SLO<select v-model="policy.sloApplicability" required @change="resetSourceSloConfirmations"><option value="" disabled>请选择</option><option value="APPLICABLE">适用</option><option value="NOT_APPLICABLE">不适用</option></select></label>
        <template v-if="policy.sloApplicability === 'APPLICABLE'">
          <label>SLO 分钟<input v-model.number="policy.sloTargetMinutes" required type="number" min="1" max="10080"></label>
          <fieldset>
            <legend>SLO 适用条件复核</legend>
            <p class="field-note">两项必须由来源管理员明确复核；任一未确认时前端不提交，服务端契约也会默认拒绝。</p>
            <label class="checkbox-confirmation"><input v-model="policy.sloAuthorizationConfirmed" name="slo-authorization-confirmed" required type="checkbox">已确认来源授权允许该 SLO</label>
            <label class="checkbox-confirmation"><input v-model="policy.sloTechnicalConditionsConfirmed" name="slo-technical-conditions-confirmed" required type="checkbox">已确认技术条件支持该 SLO</label>
          </fieldset>
        </template>
        <label v-if="policy.sloApplicability === 'NOT_APPLICABLE'">不适用原因<input v-model.trim="policy.sloReason" required maxlength="500"></label>
        <label>提交原因<input v-model.trim="policy.reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="policyOpen = false">取消</button><button class="primary-button" type="submit" form="policy-version-form" :disabled="busy || !policySloPayload">提交策略版本</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="policyDecisionOpen" title="记录策略人工决定" description="决定不可变且必须满足登记人、提交人和审批人的职责分离。">
      <form id="policy-decision-form" class="drawer-form" @submit.prevent="submitPolicyDecision">
        <label>决定<select v-model="policyDecision.outcome" required><option value="" disabled>请选择</option><option value="APPROVED">批准</option><option value="REJECTED">拒绝</option></select></label>
        <label>决定原因<input v-model.trim="policyDecision.reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="policyDecisionOpen = false">取消</button><button class="primary-button" type="submit" form="policy-decision-form" :disabled="busy">提交人工决定</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="connectorOpen" title="新建连接器配置" description="表单由版本化 Schema 控制；不接受 JSON、脚本、模板表达式或动态网络目标。">
      <ConnectorConfigEditor :definitions="connectorDefinitionOptions" @preview="previewConnector" />
      <section v-if="previewResult" class="preview-result" aria-live="polite">
        <h3>配置校验通过</h3>
        <StatusBadge
          :tone="previewResult.network_io_performed ? 'conflict' : 'verified'"
          :label="previewResult.network_io_performed ? '异常：发生网络 I/O' : '未发起网络采集'"
        />
        <dl class="metadata-list">
          <div><dt>连接器</dt><dd>{{ previewResult.connector_type }} / {{ previewResult.definition_version }}</dd></div>
          <div><dt>Schema</dt><dd>{{ previewResult.schema_version }} · {{ previewResult.schema_sha256.slice(0, 12) }}…</dd></div>
          <div v-for="row in safeConnectorConfigRows(previewResult.config)" :key="row.label"><dt>配置 · {{ row.label }}</dt><dd>{{ row.value }}</dd></div>
          <div><dt>敏感配置</dt><dd>不显示；保存后仅返回是否已配置</dd></div>
        </dl>
        <label class="connector-save-reason">保存原因<input v-model.trim="connectorSaveReason" name="connector-save-reason" required maxlength="500"></label>
      </section>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="connectorOpen = false">取消</button><button class="primary-button" type="button" :disabled="busy || !previewResult || !connectorSaveReason.trim()" @click="saveConnectorVersion">保存为新版本</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="trialOpen" title="申请试运行" description="Fixture 回放不联网；真实试运行需要独立、限时、限域审批，且遇到登录、验证码或付费墙立即停止。">
      <form id="trial-request-form" class="drawer-form" @submit.prevent="submitTrialRequest">
        <label>试运行类型<select v-model="trialRequest.kind" required><option value="" disabled>请选择</option><option v-if="hasAction('START_FIXTURE_TRIAL')" value="FIXTURE_REPLAY">Fixture 回放（不联网）</option><option v-if="hasAction('START_LIVE_TRIAL')" value="LIVE_TRIAL">真实试运行（需审批）</option></select></label>
        <label>当前已批策略<select v-model="trialRequest.policyVersionId" required><option value="" disabled>无当前已批策略</option><option v-for="version in currentApprovedPolicies" :key="version.id" :value="version.id">{{ version.policy_version }} · {{ version.status }}</option></select></label>
        <label>同策略当前配置<select v-model="trialRequest.connectorConfigVersionId" required><option value="" disabled>无同策略有效配置</option><option v-for="version in trialConnectorVersions" :key="version.id" :value="version.id">{{ version.connector_type }} · {{ version.definition_version }} · {{ version.policy_version_id }}</option></select></label>
        <label>申请原因<input v-model.trim="trialRequest.reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="trialOpen = false">取消</button><button class="primary-button" type="submit" form="trial-request-form" :disabled="busy">提交试运行申请</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="approvalOpen" title="批准生产" description="必须引用当前有效策略、连接器配置和已批准的真实试运行；服务端将重新执行职责分离与准入策略。">
      <form id="production-approval-form" class="drawer-form" @submit.prevent="submitProductionApproval">
        <label>当前已批策略<select v-model="productionApproval.policyVersionId" required><option value="" disabled>无当前已批策略</option><option v-for="version in currentApprovedPolicies" :key="version.id" :value="version.id">{{ version.policy_version }} · {{ version.status }}</option></select></label>
        <label>同策略当前配置<select v-model="productionApproval.connectorConfigVersionId" required><option value="" disabled>无同策略有效配置</option><option v-for="version in approvalConnectorVersions" :key="version.id" :value="version.id">{{ version.connector_type }} · {{ version.definition_version }} · {{ version.policy_version_id }}</option></select></label>
        <label>同版本成功真实试运行<select v-model="productionApproval.trialRunId" required><option value="" disabled>无同版本成功真实试运行</option><option v-for="run in approvalTrialRuns" :key="run.id" :value="run.id">{{ run.id }} · {{ run.status }}</option></select></label>
        <label>批准原因<input v-model.trim="productionApproval.reason" required maxlength="500"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="approvalOpen = false">取消</button><button class="primary-button" type="submit" form="production-approval-form" :disabled="busy">提交生产批准</button></div></template>
    </ResponsiveDrawer>
  </section>

  <section v-else class="source-detail-page">
    <PageHeader title="来源治理档案" eyebrow="来源中心 V2" description="正在读取服务端生命周期与治理事实。" />
    <p v-if="error" class="problem" role="alert">来源不存在、无权读取或服务暂不可用。</p>
  </section>
</template>

<style scoped>
.source-detail-page { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.detail-tabs { display: flex; max-width: 100%; gap: var(--spacing-1); overflow-x: auto; padding: var(--spacing-1); background: var(--color-surfaceMuted); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.tab-button { min-height: var(--spacing-10); flex: none; padding: var(--spacing-2) var(--spacing-4); color: var(--color-ink-700); background: transparent; border: 1px solid transparent; border-radius: var(--radius-sm); font-weight: var(--font-weight-semibold); cursor: pointer; }
.tab-button[aria-selected='true'] { color: var(--color-brand-800); background: var(--color-surface); border-color: var(--color-borderStrong); box-shadow: var(--shadow-sm); }
.tab-panel { display: grid; gap: var(--spacing-4); }
.detail-grid,
.audit-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-4); }
.panel,
.version-card { padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.panel h2,
.section-heading h2,
.version-card h3,
.preview-result h3 { margin: 0; color: var(--color-ink-900); }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: var(--spacing-4); }
.section-heading p { margin: var(--spacing-1) 0 0; color: var(--color-ink-600); }
.metadata-list { display: grid; gap: 0; margin: var(--spacing-3) 0 0; }
.metadata-list div { display: grid; grid-template-columns: minmax(8rem, 0.8fr) 1.2fr; gap: var(--spacing-3); padding: var(--spacing-3) 0; border-top: 1px solid var(--color-border); }
dt { color: var(--color-ink-600); }
dd { margin: 0; color: var(--color-ink-900); font-family: var(--font-mono); overflow-wrap: anywhere; }
.missing-list { margin: var(--spacing-4) 0 0; padding: var(--spacing-3) var(--spacing-3) var(--spacing-3) var(--spacing-8); color: var(--color-conflict-700); background: var(--color-conflict-50); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: var(--text-xs); }
.field-note,
.empty-copy { margin: var(--spacing-3) 0 0; color: var(--color-ink-600); font-size: var(--text-sm); }
.read-only-note,
.isolation-note,
.form-note { margin: 0; padding: var(--spacing-3); color: var(--color-ink-700); background: var(--color-surfaceMuted); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.version-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-4); }
.policy-version-cards { grid-template-columns: 1fr; }
.version-card__title { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-3); }
.policy-evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--spacing-3); margin-top: var(--spacing-4); }
.policy-evidence-grid section { padding: var(--spacing-3); background: var(--color-surfaceMuted); border-radius: var(--radius-sm); }
.policy-evidence-grid h4 { margin: 0; color: var(--color-ink-900); }
.policy-decision-button { margin-top: var(--spacing-4); }
.table-scroll { max-width: 100%; overflow-x: auto; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.table-scroll:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
table { width: 100%; min-width: 50rem; border-collapse: collapse; }
th,
td { padding: var(--spacing-3) var(--spacing-4); color: var(--color-ink-700); text-align: left; border-bottom: 1px solid var(--color-border); }
thead th { color: var(--color-ink-900); background: var(--color-surfaceMuted); font-size: var(--text-xs); }
.event-list { display: grid; gap: var(--spacing-3); margin: var(--spacing-4) 0 0; padding: 0; list-style: none; }
.event-list li { padding: var(--spacing-3); background: var(--color-surfaceMuted); border-radius: var(--radius-sm); }
.event-list li > div { display: flex; justify-content: space-between; gap: var(--spacing-3); }
.event-list p { margin: var(--spacing-2) 0; color: var(--color-ink-700); }
.event-list span,
.event-list time { color: var(--color-ink-600); font-family: var(--font-mono); font-size: var(--text-xs); }
.drawer-form { display: grid; gap: var(--spacing-4); }
.drawer-form label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); }
.drawer-form input,
.drawer-form select { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-ink-900); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.drawer-form .checkbox-confirmation { display: flex; align-items: center; gap: var(--spacing-2); }
.drawer-form .checkbox-confirmation input { width: var(--spacing-4); min-height: auto; height: var(--spacing-4); padding: 0; }
.drawer-form fieldset { display: grid; gap: var(--spacing-3); margin: 0; padding: var(--spacing-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.drawer-form legend { padding-inline: var(--spacing-2); color: var(--color-ink-900); font-weight: var(--font-weight-semibold); }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-3); }
.drawer-actions { display: flex; justify-content: flex-end; gap: var(--spacing-2); }
.preview-result { display: grid; gap: var(--spacing-3); margin-top: var(--spacing-5); padding: var(--spacing-4); background: var(--color-surfaceMuted); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.connector-save-reason { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); }
.connector-save-reason input { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-ink-900); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.primary-button,
.secondary-button,
.text-button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-4); font-weight: var(--font-weight-semibold); border: 1px solid currentColor; border-radius: var(--radius-sm); cursor: pointer; }
.primary-button { color: var(--color-surface); background: var(--color-brand-700); border-color: var(--color-brand-700); }
.secondary-button,
.text-button { color: var(--color-brand-700); background: var(--color-surface); }
.text-button { min-height: auto; padding: var(--spacing-1) var(--spacing-2); font-size: var(--text-xs); }
button:disabled { cursor: wait; opacity: 0.6; }
.problem { margin: 0; padding: var(--spacing-3); color: var(--color-conflict-700); background: var(--color-conflict-50); border: 1px solid currentColor; border-radius: var(--radius-sm); }

@media (max-width: 60rem) {
  .detail-grid,
  .audit-grid,
  .version-cards,
  .policy-evidence-grid { grid-template-columns: 1fr; }
}

@media (max-width: 42rem) {
  .section-heading { align-items: stretch; flex-direction: column; }
  .metadata-list div,
  .field-grid { grid-template-columns: 1fr; gap: var(--spacing-1); }
}
</style>
