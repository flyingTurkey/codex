<script setup lang="ts">
import type {
  DiscoveryChannel,
  MeResponse,
  QualificationVerdict,
  SourceAttentionPage,
  SourceCandidateBatchDecisionResult,
  SourceCandidateBatchDecisionRequest,
  SourceCandidateCreateRequest,
  SourceCandidatePage,
  SourceCandidateQualificationRequest,
  SourceCandidateStatus,
  SourceContentDomain,
  SourceIndustry,
  SourceStreamPage,
} from '@srbg/contracts'
import { EmptyState, PageHeader, ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { computed, reactive, ref, watch } from 'vue'

import SourceCandidateCard from '../../../components/SourceCandidateCard.vue'
import SourceCandidateDrawer from '../../../components/SourceCandidateDrawer.vue'
import SourceWorkspaceTabs from '../../../components/SourceWorkspaceTabs.vue'
import type {
  SourceAttentionCardProjection,
  SourceCandidateCardProjection,
  SourceStreamCardProjection,
  SourceWorkspaceView,
} from '../../../source-center'
import {
  apiProblemMessage,
  apiProblemStatus,
  attentionTone,
  formatShanghaiDateTime,
  sourceStreamTone,
  workspaceViewOf,
} from '../../../source-center'
import { useSourceCenterWorkspace } from '../../../composables/useSourceCenterWorkspace'
import { createUuidV7 } from '../../../utils/uuid-v7'

type SourceWorkspacePage = SourceAttentionPage | SourceCandidatePage | SourceStreamPage

const candidateStatuses: readonly SourceCandidateStatus[] = [
  'DISCOVERED',
  'QUALIFYING',
  'READY_FOR_DECISION',
  'ENABLED',
  'DISMISSED',
  'BLOCKED',
  'STALE',
]
const contentDomains: readonly SourceContentDomain[] = [
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
]
const discoveryChannels: readonly DiscoveryChannel[] = [
  'DIRECTORY',
  'RSS',
  'SITEMAP',
  'OUTBOUND_LINK',
  'MANUAL',
  'BAIDU_SEARCH',
]
const industries: readonly SourceIndustry[] = [
  'HIGHWAY',
  'BRIDGE',
  'TUNNEL',
  'RAILWAY',
  'RAIL_TRANSIT',
  'WATER_CONSERVANCY',
  'MUNICIPAL',
  'BUILDING',
  'ENERGY',
  'PORT_WATERWAY',
  'AIRPORT',
  'GENERAL_TRANSPORT',
  'UNKNOWN',
]
const qualificationVerdicts: readonly QualificationVerdict[] = [
  'QUALIFIED',
  'WARN_WAIVABLE',
  'BLOCKED',
]

const route = useRoute()
const workspace = useSourceCenterWorkspace(route.query.view)
const selectedCandidate = ref<SourceCandidateCardProjection | null>(null)
const pendingDecision = ref<'' | 'DISMISS' | 'ENABLE'>('')
const decisionDrawerOpen = ref(false)
const discoveryDrawerOpen = ref(false)
const actionError = ref<string | null>(null)
const actionMessage = ref<string | null>(null)
const busyCandidateId = ref<string | null>(null)
const submittingDiscovery = ref(false)
const selectedCandidateIds = ref<string[]>([])

const draftFilters = reactive({
  contentDomain: '',
  discoveryChannel: '',
  industry: '',
  languageTag: '',
  query: '',
  status: '',
  verdict: '',
})
const discovery = reactive({ canonicalUrl: '', reason: '' })

const { data: identity } = await useFetch<MeResponse>('/api/v1/me', {
  retry: 0,
  timeout: 2_000,
})
const roles = computed(() => identity.value?.roles ?? [])
const canSubmitDiscovery = computed(() => roles.value.some(role => (
  role === 'source_admin' || role === 'platform_admin'
)))
const isPlatformAdmin = computed(() => roles.value.includes('platform_admin'))

const {
  data: workspacePage,
  error: workspaceError,
  refresh: refreshWorkspace,
  status: workspaceStatus,
} = await useFetch<SourceWorkspacePage>(
  workspace.endpoint,
  {
    default: () => ({ has_more: false, items: [], next_cursor: null }),
    retry: 0,
    timeout: 5_000,
  },
)

const viewCounts = reactive<Record<SourceWorkspaceView, number>>({
  attention: 0,
  candidates: 0,
  enabled: 0,
})
watch(
  [workspace.activeView, () => workspacePage.value.items.length],
  ([view, count]) => { viewCounts[view] = count },
  { immediate: true },
)
watch(
  () => route.query.view,
  value => workspace.changeView(workspaceViewOf(value)),
)

const candidateItems = computed(() => workspace.activeView.value === 'candidates'
  ? workspacePage.value.items as readonly SourceCandidateCardProjection[]
  : [])
const streamItems = computed(() => workspace.activeView.value === 'enabled'
  ? workspacePage.value.items as readonly SourceStreamCardProjection[]
  : [])
const attentionItems = computed(() => workspace.activeView.value === 'attention'
  ? workspacePage.value.items as readonly SourceAttentionCardProjection[]
  : [])
const selectedCandidates = computed(() => candidateItems.value.filter(candidate => (
  selectedCandidateIds.value.includes(candidate.id)
)))
const batchRuleVersion = computed(() => selectedCandidates.value[0]
  ?.latest_qualification?.rule_version ?? '')
const canBatchEnable = computed(() => (
  isPlatformAdmin.value
  && selectedCandidates.value.length > 0
  && selectedCandidates.value.length <= 10
  && selectedCandidates.value.every(candidate => (
    candidate.batch_enable_eligible
    && candidate.latest_qualification?.rule_version === batchRuleVersion.value
  ))
))

async function changeView(view: SourceWorkspaceView): Promise<void> {
  if (workspace.activeView.value === view) return
  workspace.changeView(view)
  selectedCandidateIds.value = []
  actionError.value = null
  await navigateTo({
    path: route.path,
    query: { ...route.query, view },
  }, { replace: true })
}

function applyFilters(): void {
  workspace.filters.q = draftFilters.query.trim()
  workspace.filters.industry = draftFilters.industry
  workspace.filters.content_domain = draftFilters.contentDomain
  workspace.filters.discovery_channel = draftFilters.discoveryChannel
  workspace.filters.language_tag = draftFilters.languageTag
  workspace.filters.status = draftFilters.status
  workspace.filters.verdict = draftFilters.verdict
  workspace.resetCursor()
  selectedCandidateIds.value = []
}

function resetFilters(): void {
  Object.assign(draftFilters, {
    contentDomain: '',
    discoveryChannel: '',
    industry: '',
    languageTag: '',
    query: '',
    status: '',
    verdict: '',
  })
  applyFilters()
}

function nextPage(): void {
  if (workspacePage.value.next_cursor) workspace.cursor.value = workspacePage.value.next_cursor
}

function openDecision(
  candidate: SourceCandidateCardProjection,
  decision: 'DISMISS' | 'ENABLE',
): void {
  selectedCandidate.value = candidate
  pendingDecision.value = decision
  actionError.value = null
  decisionDrawerOpen.value = true
}

async function handleCandidateDecision(payload: {
  decision: 'DISMISS' | 'ENABLE'
  reason: string
  waiverReason?: string
}): Promise<void> {
  const candidate = selectedCandidate.value
  const bundle = candidate?.latest_qualification
  if (!candidate || (payload.decision === 'ENABLE' && !bundle)) return

  busyCandidateId.value = candidate.id
  actionError.value = null
  actionMessage.value = null
  try {
    await workspace.candidateDecision({
      candidateId: candidate.id,
      decision: payload.decision,
      reason: payload.reason,
      waiverReason: payload.waiverReason,
      ...(bundle ? { expectedBundleSha256: bundle.bundle_sha256 } : {}),
    }, {
      fetcher: (url, options) => $fetch(url, options),
      refresh: refreshWorkspace,
    })
    decisionDrawerOpen.value = false
    selectedCandidate.value = null
    pendingDecision.value = ''
    actionMessage.value = payload.decision === 'ENABLE'
      ? '来源已启用，首次生产重抓已进入队列。'
      : '候选已标记为不启用。'
  } catch (error) {
    const status = apiProblemStatus(error)
    if (status === 409) {
      decisionDrawerOpen.value = false
      selectedCandidate.value = null
      pendingDecision.value = ''
      actionError.value = '资格包已变化或过期。列表已刷新，请重新核对后再决定；旧决定未重试。'
    } else if (status === 403) {
      actionError.value = '该决定仅限完成近期二次验证的平台管理员。'
    } else {
      actionError.value = apiProblemMessage(error)
    }
  } finally {
    busyCandidateId.value = null
  }
}

async function requestQualification(candidate: SourceCandidateCardProjection): Promise<void> {
  busyCandidateId.value = candidate.id
  actionError.value = null
  actionMessage.value = null
  try {
    const payload: SourceCandidateQualificationRequest = {
      reason: '管理员请求按当前规则重新执行资格审核',
    }
    await $fetch(`/api/v1/admin/source-candidates/${candidate.id}/qualification-runs`, {
      method: 'POST',
      body: payload,
      headers: { 'Idempotency-Key': createUuidV7() },
      retry: 0,
      timeout: 5_000,
    })
    await refreshWorkspace()
    actionMessage.value = '资格审核已进入隔离队列。'
  } catch (error) {
    actionError.value = apiProblemMessage(error)
  } finally {
    busyCandidateId.value = null
  }
}

function toggleCandidate(candidate: SourceCandidateCardProjection, selected: boolean): void {
  const existing = new Set(selectedCandidateIds.value)
  if (!selected) {
    existing.delete(candidate.id)
    selectedCandidateIds.value = [...existing]
    return
  }
  const ruleVersion = candidate.latest_qualification?.rule_version
  if (batchRuleVersion.value && batchRuleVersion.value !== ruleVersion) {
    actionError.value = '批量启用只能选择同一资格规则版本的全绿候选。'
    return
  }
  if (existing.size >= 10) {
    actionError.value = '单次最多批量启用 10 个候选；请先处理当前选择。'
    return
  }
  existing.add(candidate.id)
  selectedCandidateIds.value = [...existing]
}

async function batchEnable(): Promise<void> {
  if (!canBatchEnable.value) return
  actionError.value = null
  actionMessage.value = null
  try {
    const payload: SourceCandidateBatchDecisionRequest = {
      expected_rule_version: batchRuleVersion.value,
      reason: '批量启用同一规则版本的全绿资格候选',
      targets: selectedCandidates.value.map(candidate => ({
        candidate_id: candidate.id,
        expected_bundle_sha256: candidate.latest_qualification!.bundle_sha256,
      })),
    }
    const result = await $fetch<SourceCandidateBatchDecisionResult>(
      '/api/v1/admin/source-candidates/batch-decisions',
      {
        method: 'POST',
        body: payload,
        headers: { 'Idempotency-Key': createUuidV7() },
        retry: 0,
        timeout: 10_000,
      },
    )
    const failedItems = result.items.filter(item => item.outcome !== 'APPLIED')
    selectedCandidateIds.value = failedItems.map(item => item.candidate_id)
    await refreshWorkspace()
    actionMessage.value = `批量决定已逐项处理：${result.items.length - failedItems.length} 项启用，${failedItems.length} 项未启用。`
    if (failedItems.length) {
      actionError.value = `未启用候选：${failedItems.map(item => `${item.candidate_id}（${item.reason_code ?? item.outcome}）`).join('；')}`
    }
  } catch (error) {
    if (apiProblemStatus(error) === 409) await refreshWorkspace()
    actionError.value = apiProblemMessage(error)
  }
}

async function submitDiscovery(): Promise<void> {
  if (!canSubmitDiscovery.value) return
  submittingDiscovery.value = true
  actionError.value = null
  try {
    const payload: SourceCandidateCreateRequest = {
      url: discovery.canonicalUrl.trim(),
      reason: discovery.reason.trim(),
    }
    await $fetch('/api/v1/admin/source-candidates', {
      method: 'POST',
      body: payload,
      headers: { 'Idempotency-Key': createUuidV7() },
      retry: 0,
      timeout: 5_000,
    })
    discoveryDrawerOpen.value = false
    Object.assign(discovery, { canonicalUrl: '', reason: '' })
    workspace.changeView('candidates')
    await refreshWorkspace()
    actionMessage.value = 'URL 已进入候选发现与隔离资格审核流程。'
  } catch (error) {
    actionError.value = apiProblemMessage(error)
  } finally {
    submittingDiscovery.value = false
  }
}
</script>

<template>
  <section class="source-workspace-page">
    <PageHeader
      title="来源中心"
      eyebrow="自动扩源"
      description="系统自动发现并在隔离域完成资格试采；来源管理员负责运营，只有平台管理员能作出最终启用决定。"
    >
      <template #status>
        <StatusBadge tone="verified" label="服务端资格包" />
        <span>当前页 {{ workspacePage.items.length }} 项</span>
      </template>
      <template #actions>
        <NuxtLink class="secondary-button" to="/admin/sources/coverage">查看覆盖缺口</NuxtLink>
        <button
          v-if="canSubmitDiscovery"
          class="primary-button"
          type="button"
          @click="discoveryDrawerOpen = true"
        >
          提交发现 URL
        </button>
      </template>
    </PageHeader>

    <SourceWorkspaceTabs
      :active-view="workspace.activeView.value"
      :counts="viewCounts"
      @change="changeView"
    />

    <form
      v-if="workspace.activeView.value !== 'attention'"
      class="source-workspace-filters"
      aria-label="来源工作区筛选"
      @submit.prevent="applyFilters"
    >
      <label>
        搜索
        <input v-model.trim="draftFilters.query" name="source-query" maxlength="200" placeholder="机构、域名或来源名称">
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        工程行业
        <select v-model="draftFilters.industry" name="source-industry">
          <option value="">全部</option>
          <option v-for="industry in industries" :key="industry" :value="industry">{{ industry }}</option>
        </select>
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        内容域
        <select v-model="draftFilters.contentDomain" name="source-content-domain">
          <option value="">全部</option>
          <option v-for="domain in contentDomains" :key="domain" :value="domain">{{ domain }}</option>
        </select>
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        状态
        <select v-model="draftFilters.status" name="source-status">
          <option value="">全部</option>
          <option v-for="option in candidateStatuses" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        资格结论
        <select v-model="draftFilters.verdict" name="source-verdict">
          <option value="">全部</option>
          <option v-for="verdict in qualificationVerdicts" :key="verdict" :value="verdict">{{ verdict }}</option>
        </select>
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        发现渠道
        <select v-model="draftFilters.discoveryChannel" name="source-discovery-channel">
          <option value="">全部</option>
          <option v-for="channel in discoveryChannels" :key="channel" :value="channel">{{ channel }}</option>
        </select>
      </label>
      <label v-if="workspace.activeView.value === 'candidates'">
        语言标签
        <input
          v-model.trim="draftFilters.languageTag"
          name="source-language-tag"
          maxlength="35"
          pattern="[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*"
          placeholder="zh-CN"
        >
      </label>
      <div class="source-workspace-filters__actions">
        <button class="secondary-button" type="button" @click="resetFilters">重置</button>
        <button class="primary-button" type="submit">应用筛选</button>
      </div>
    </form>

    <p v-if="actionMessage" class="success" role="status">{{ actionMessage }}</p>
    <p v-if="actionError" class="problem" role="alert">{{ actionError }}</p>
    <div v-if="workspaceError" class="problem" role="alert">
      当前队列暂不可用；不会使用浏览器缓存或演示数据替代服务端事实。
      <button type="button" @click="refreshWorkspace()">重试</button>
    </div>
    <p v-else-if="workspaceStatus === 'pending'" class="loading" aria-live="polite">正在读取来源队列…</p>

    <section
      v-else-if="workspace.activeView.value === 'candidates'"
      id="source-workspace-panel-candidates"
      role="tabpanel"
      aria-labelledby="source-workspace-tab-candidates"
      class="source-workspace-panel"
    >
      <div v-if="selectedCandidateIds.length" class="batch-bar" role="region" aria-label="批量启用候选">
        <span>已选择 {{ selectedCandidateIds.length }} 项 · {{ batchRuleVersion }}</span>
        <button class="primary-button" type="button" :disabled="!canBatchEnable" @click="batchEnable">
          批量启用全绿候选
        </button>
      </div>
      <EmptyState
        v-if="candidateItems.length === 0"
        title="当前没有候选来源"
        description="系统会继续从公开目录、RSS、Sitemap、外链、人工 URL 和搜索服务发现候选。"
        icon="Search"
      />
      <div v-else class="candidate-grid" aria-label="候选来源">
        <SourceCandidateCard
          v-for="candidate in candidateItems"
          :key="candidate.id"
          :candidate="candidate"
          :roles="roles"
          :busy="busyCandidateId === candidate.id"
          :selected="selectedCandidateIds.includes(candidate.id)"
          @decision="openDecision(candidate, $event)"
          @qualification="requestQualification(candidate)"
          @select="toggleCandidate(candidate, $event)"
        />
      </div>
    </section>

    <section
      v-else-if="workspace.activeView.value === 'enabled'"
      id="source-workspace-panel-enabled"
      role="tabpanel"
      aria-labelledby="source-workspace-tab-enabled"
      class="source-workspace-panel"
    >
      <EmptyState
        v-if="streamItems.length === 0"
        title="当前没有已启用采集流"
        description="候选通过资格审核并由平台管理员启用后，将在这里显示生产采集状态。"
        icon="Database"
      />
      <div v-else class="stream-list" aria-label="已启用来源流">
        <article v-for="stream in streamItems" :key="stream.id" class="stream-row">
          <div>
            <p>{{ stream.stream_key }} · {{ stream.authorization_boundary }}</p>
            <h2>{{ stream.institution_name }}</h2>
            <a :href="stream.canonical_url" target="_blank" rel="noopener noreferrer">{{ stream.canonical_url }}</a>
          </div>
          <dl>
            <div><dt>最近成功</dt><dd>{{ formatShanghaiDateTime(stream.last_success_at) }}</dd></div>
            <div><dt>最近失败</dt><dd>{{ formatShanghaiDateTime(stream.last_failure_at) }}</dd></div>
            <div><dt>连续失败</dt><dd>{{ stream.consecutive_failure_count ?? 0 }}</dd></div>
            <div><dt>下次采集</dt><dd>{{ formatShanghaiDateTime(stream.next_fetch_at) }}</dd></div>
          </dl>
          <div class="stream-row__status">
            <StatusBadge :tone="sourceStreamTone(stream)" :label="stream.status" />
            <NuxtLink class="secondary-button" :to="`/admin/sources/${stream.source_id}`">查看机构</NuxtLink>
          </div>
          <p class="stream-row__reason">规则 {{ stream.rule_version }} · {{ (stream.available_actions ?? []).join(' / ') || '只读' }}</p>
        </article>
      </div>
    </section>

    <section
      v-else
      id="source-workspace-panel-attention"
      role="tabpanel"
      aria-labelledby="source-workspace-tab-attention"
      class="source-workspace-panel"
    >
      <EmptyState
        v-if="attentionItems.length === 0"
        title="当前没有需处理项"
        description="自动暂停、规则变化、可豁免警告和自愈失败会进入此队列。"
        icon="CheckCircle"
      />
      <div v-else class="attention-list" aria-label="来源需处理队列">
        <article v-for="item in attentionItems" :key="`${item.stream.id}:${item.last_observed_at}`" class="attention-card">
          <div class="attention-card__title">
            <div>
              <p>{{ item.stream.stream_key }} · {{ item.stream.authorization_boundary }}</p>
              <h2>{{ item.stream.institution_name }}</h2>
            </div>
            <StatusBadge :tone="attentionTone(item)" :label="item.stream.status" />
          </div>
          <ul class="attention-card__reasons" aria-label="需处理原因">
            <li v-for="reasonCode in item.reason_codes" :key="reasonCode">{{ reasonCode }}</li>
          </ul>
          <div class="attention-card__meta">
            <span>首次 {{ formatShanghaiDateTime(item.first_observed_at) }}</span>
            <span>最近 {{ formatShanghaiDateTime(item.last_observed_at) }}</span>
            <span>{{ (item.stream.available_actions ?? []).join(' / ') || '只读关注项' }}</span>
            <NuxtLink :to="`/admin/sources/${item.stream.source_id}`">查看来源</NuxtLink>
          </div>
        </article>
      </div>
    </section>

    <div v-if="workspacePage.has_more" class="pagination-actions">
      <button class="secondary-button" type="button" @click="nextPage">加载下一页</button>
    </div>

    <SourceCandidateDrawer
      v-if="selectedCandidate"
      v-model="decisionDrawerOpen"
      :candidate="selectedCandidate"
      :initial-decision="pendingDecision"
      :roles="roles"
      :busy="busyCandidateId === selectedCandidate.id"
      @decision="handleCandidateDecision"
    />

    <ResponsiveDrawer
      v-model="discoveryDrawerOpen"
      title="提交发现 URL"
      description="只登记公开目标并启动隔离资格审核；不会直接创建生产来源或发布内容。"
    >
      <form id="candidate-discovery-form" class="discovery-form" @submit.prevent="submitDiscovery">
        <label>
          公开 URL
          <input v-model.trim="discovery.canonicalUrl" name="candidate-url" type="url" required maxlength="2048" placeholder="https://example.gov.cn/">
        </label>
        <label>
          提交原因
          <textarea v-model.trim="discovery.reason" name="candidate-reason" required minlength="2" maxlength="500" rows="5" />
        </label>
        <p role="note">平台将自行规范化 URL、验证公网边界、保存证据并生成资格包；客户端不能声明已批准或已启用。</p>
      </form>
      <template #footer>
        <div class="drawer-actions">
          <button class="secondary-button" type="button" @click="discoveryDrawerOpen = false">取消</button>
          <button class="primary-button" type="submit" form="candidate-discovery-form" :disabled="submittingDiscovery">
            {{ submittingDiscovery ? '正在提交…' : '提交并开始资格审核' }}
          </button>
        </div>
      </template>
    </ResponsiveDrawer>
  </section>
</template>

<style scoped>
.source-workspace-page,
.source-workspace-panel,
.candidate-grid,
.stream-list,
.attention-list,
.discovery-form {
  display: grid;
  gap: var(--spacing-4);
}

.source-workspace-page {
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.source-workspace-filters {
  display: grid;
  grid-template-columns: minmax(14rem, 1.5fr) repeat(3, minmax(10rem, 1fr)) auto;
  align-items: end;
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-3);
}

.source-workspace-filters label,
.discovery-form label {
  display: grid;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  gap: var(--spacing-1);
}

.source-workspace-filters input,
.source-workspace-filters select,
.discovery-form input,
.discovery-form textarea {
  width: 100%;
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.source-workspace-filters__actions,
.drawer-actions,
.batch-bar,
.pagination-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.batch-bar {
  position: sticky;
  z-index: 2;
  top: var(--spacing-2);
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-brand-800);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
}

.stream-row,
.attention-card {
  display: grid;
  padding: var(--spacing-4) var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-3);
}

.stream-row {
  grid-template-columns: minmax(16rem, 1.3fr) minmax(18rem, 1fr) auto;
  align-items: center;
}

.stream-row h2,
.stream-row p,
.attention-card h2,
.attention-card p {
  margin: 0;
}

.stream-row h2,
.attention-card h2 {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
}

.stream-row > div:first-child > p,
.attention-card__title p,
.attention-card__meta {
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.attention-card__reasons {
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  padding: 0;
  color: var(--color-conflict-700);
  list-style: none;
  gap: var(--spacing-2);
}

.attention-card__reasons li {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-conflict-50);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.stream-row a {
  display: block;
  overflow: hidden;
  margin-top: var(--spacing-1);
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stream-row dl {
  display: grid;
  margin: 0;
  gap: var(--spacing-2);
}

.stream-row dl div {
  display: grid;
  grid-template-columns: 7rem 1fr;
  gap: var(--spacing-2);
}

.stream-row dt {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.stream-row dd {
  margin: 0;
  color: var(--color-ink-900);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.stream-row__status {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.stream-row__reason {
  grid-column: 1 / -1;
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-reviewPending-700);
  background: var(--color-reviewPending-50);
  border-radius: var(--radius-sm);
}

.attention-card__title,
.attention-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.attention-card__meta {
  justify-content: flex-start;
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--color-border);
}

.problem,
.success {
  margin: 0;
  padding: var(--spacing-3);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
}

.problem {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.success {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
}

.loading {
  padding: var(--spacing-8);
  color: var(--color-ink-600);
  text-align: center;
}

.primary-button,
.secondary-button {
  display: inline-flex;
  min-height: var(--spacing-10);
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
  cursor: pointer;
}

.primary-button {
  color: var(--color-surface);
  background: var(--color-brand-700);
}

.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

@media (max-width: 79.999rem) {
  .source-workspace-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stream-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .stream-row dl {
    grid-column: 1 / -1;
  }
}

@media (max-width: 47.999rem) {
  .source-workspace-filters,
  .stream-row {
    grid-template-columns: 1fr;
  }

  .source-workspace-filters__actions,
  .stream-row__status {
    justify-content: stretch;
  }

  .source-workspace-filters__actions > *,
  .stream-row__status > * {
    flex: 1;
  }
}
</style>
