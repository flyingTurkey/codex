<script setup lang="ts">
import type { MeResponse } from '@srbg/contracts'
import { EmptyState, PageHeader, ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { computed, reactive, ref } from 'vue'

import type { SourceCenterDetail, SourceCenterSummary, SourceLifecycleDisplayState } from '../../../source-center'
import {
  apiProblemMessage,
  lifecycleLabel,
  lifecycleStateOf,
  lifecycleTone,
  runtimeAuthorizationLabel,
  runtimeAuthorizationTone,
} from '../../../source-center'

const drawerOpen = ref(false)
const submitting = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  baseUrl: '',
  channel: '' as '' | 'BOTH' | 'DIGITAL' | 'SAFETY',
  collectionMethod: '',
  contentDomain: '',
  countryCode: '',
  governanceOwnerId: '',
  industry: '',
  languageTag: '',
  name: '',
  pollIntervalMinutes: '' as '' | number,
  priority: '' as '' | 'P0' | 'P1' | 'P2',
  regionCode: '',
  sourceRole: '',
  sourceType: '',
})

const filters = reactive({
  contentDomain: '',
  industry: '',
  lifecycle: '' as '' | SourceLifecycleDisplayState,
  regionLanguage: '',
  sourceType: '',
})

const { data: identity } = await useFetch<MeResponse>('/api/v1/me', {
  retry: 0,
  timeout: 2_000,
})
const canManage = computed(() => identity.value?.roles.some(role =>
  role === 'source_admin' || role === 'platform_admin',
) ?? false)

const {
  data: sources,
  error,
  refresh,
  status,
} = await useFetch<SourceCenterSummary[]>('/api/v1/admin/sources', {
  default: () => [],
  retry: 0,
  timeout: 5_000,
})

function uniqueValues(values: readonly (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort()
}

const lifecycleOptions: readonly SourceLifecycleDisplayState[] = [
  'CANDIDATE',
  'COMPLIANCE_REVIEW',
  'TRIAL',
  'ACTIVE',
  'PAUSED',
  'RETIRED',
  'UNKNOWN',
]
const industryOptions = computed(() => uniqueValues(sources.value.flatMap(source => source.industries ?? [])))
const contentDomainOptions = computed(() => uniqueValues(sources.value.flatMap(source => source.content_domains ?? [])))
const sourceTypeOptions = computed(() => uniqueValues(sources.value.map(source => source.source_type)))
const regionLanguageOptions = computed(() => uniqueValues(sources.value.flatMap(source =>
  (source.region_codes ?? ['UNKNOWN']).flatMap(region =>
    (source.language_tags ?? ['UNKNOWN']).map(language => `${region} / ${language}`),
  ),
)))

const filteredSources = computed(() => sources.value.filter((source) => {
  if (filters.lifecycle && lifecycleStateOf(source) !== filters.lifecycle) return false
  if (filters.industry && !(source.industries ?? []).some(value => value === filters.industry)) return false
  if (filters.contentDomain && !(source.content_domains ?? []).some(value => value === filters.contentDomain)) return false
  if (filters.sourceType && source.source_type !== filters.sourceType) return false
  if (filters.regionLanguage) {
    const combinations = (source.region_codes ?? ['UNKNOWN']).flatMap(region =>
      (source.language_tags ?? ['UNKNOWN']).map(language => `${region} / ${language}`),
    )
    if (!combinations.includes(filters.regionLanguage)) return false
  }
  return true
}))

function resetForm(): void {
  Object.assign(form, {
    baseUrl: '',
    channel: '',
    collectionMethod: '',
    contentDomain: '',
    countryCode: '',
    governanceOwnerId: '',
    industry: '',
    languageTag: '',
    name: '',
    pollIntervalMinutes: '',
    priority: '',
    regionCode: '',
    sourceRole: '',
    sourceType: '',
  })
}

async function submitSource(): Promise<void> {
  submitting.value = true
  formError.value = null
  try {
    const created = await $fetch<SourceCenterDetail>('/api/v1/admin/sources', {
      method: 'POST',
      body: {
        authority_level: 'UNKNOWN',
        base_url: form.baseUrl,
        channel: form.channel,
        collection_method: form.collectionMethod,
        content_domains: [form.contentDomain],
        country_codes: [form.countryCode],
        declared_roles: [form.sourceRole],
        governance_owner_id: form.governanceOwnerId,
        industries: [form.industry],
        language_tags: [form.languageTag],
        name: form.name,
        owner: form.governanceOwnerId,
        poll_interval_minutes: form.pollIntervalMinutes,
        priority: form.priority,
        region_codes: [form.regionCode],
        source_type: form.sourceType,
      },
      timeout: 5_000,
    })
    drawerOpen.value = false
    resetForm()
    await refresh()
    await navigateTo(`/admin/sources/${created.id}`)
  } catch (requestError) {
    formError.value = apiProblemMessage(requestError)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="source-registry-page">
    <PageHeader
      title="来源中心 V2"
      eyebrow="来源治理"
      description="登记、合规复核、试运行、批准、暂停和退役均由服务端治理事实驱动；客户端自报状态不产生生产授权。"
    >
      <template #status>
        <StatusBadge tone="pending" label="默认拒绝" />
        <span>{{ sources.length }} 个治理档案</span>
      </template>
      <template #actions>
        <NuxtLink class="secondary-button" to="/admin/sources/coverage">查看覆盖缺口</NuxtLink>
        <button v-if="canManage" class="primary-button" type="button" @click="drawerOpen = true">
          登记候选来源
        </button>
      </template>
    </PageHeader>

    <div v-if="error" class="problem" role="alert">
      来源列表暂不可用。系统不会用客户端缓存或演示数据替代治理事实。
      <button type="button" @click="refresh()">重试</button>
    </div>

    <div v-else-if="status === 'pending'" class="loading" aria-live="polite">正在读取来源…</div>

    <template v-else>
      <form class="source-filters" aria-label="来源筛选" @submit.prevent>
        <label>
          生命周期
          <select v-model="filters.lifecycle">
            <option value="">全部</option>
            <option v-for="state in lifecycleOptions" :key="state" :value="state">{{ state }}</option>
          </select>
        </label>
        <label>
          工程行业
          <select v-model="filters.industry">
            <option value="">全部</option>
            <option v-for="industry in industryOptions" :key="industry" :value="industry">{{ industry }}</option>
          </select>
        </label>
        <label>
          内容域
          <select v-model="filters.contentDomain">
            <option value="">全部</option>
            <option v-for="domain in contentDomainOptions" :key="domain" :value="domain">{{ domain }}</option>
          </select>
        </label>
        <label>
          来源类型
          <select v-model="filters.sourceType">
            <option value="">全部</option>
            <option v-for="sourceType in sourceTypeOptions" :key="sourceType" :value="sourceType">{{ sourceType }}</option>
          </select>
        </label>
        <label>
          地区 / 语言
          <select v-model="filters.regionLanguage">
            <option value="">全部</option>
            <option v-for="value in regionLanguageOptions" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
      </form>

      <EmptyState
        v-if="sources.length === 0"
        title="还没有登记来源"
        description="新登记来源只会成为 CANDIDATE；缺少明确治理材料时保持生产拒绝。"
        icon="Database"
      />

      <EmptyState
        v-else-if="filteredSources.length === 0"
        title="没有符合条件的来源"
        description="调整筛选条件，或到覆盖矩阵查看尚未补齐的维度。"
        icon="Search"
      />

      <div v-else class="source-list" aria-label="来源列表">
        <NuxtLink
          v-for="source in filteredSources"
          :key="source.id"
          class="source-row"
          :to="`/admin/sources/${source.id}`"
        >
          <div class="source-row__identity">
            <span class="source-code">{{ source.registry_code ?? 'CUSTOM' }}</span>
            <strong>{{ source.name }}</strong>
            <span>{{ source.base_url }}</span>
          </div>
          <div class="source-row__dimensions">
            <span>{{ source.industries?.join(' / ') || 'UNKNOWN' }}</span>
            <span>{{ source.content_domains?.join(' / ') || 'UNKNOWN' }}</span>
            <span>{{ source.region_codes?.join(' / ') || 'UNKNOWN' }} · {{ source.language_tags?.join(' / ') || 'UNKNOWN' }}</span>
          </div>
          <div class="source-row__status">
            <StatusBadge :tone="lifecycleTone(source)" :label="lifecycleLabel(source)" />
            <StatusBadge
              :tone="runtimeAuthorizationTone(source)"
              :label="runtimeAuthorizationLabel(source)"
            />
          </div>
        </NuxtLink>
      </div>
    </template>

    <ResponsiveDrawer
      v-model="drawerOpen"
      title="登记候选来源"
      description="仅登记治理档案；不批准、不试运行，也不发起任何网络请求。来源权威初始为 UNKNOWN。"
    >
      <form id="source-create-form" class="source-form" @submit.prevent="submitSource">
        <label>来源名称<input v-model.trim="form.name" required maxlength="200"></label>
        <label>公开基础 URL<input v-model.trim="form.baseUrl" required type="url" maxlength="2048"></label>
        <label>治理责任人 ID<input v-model.trim="form.governanceOwnerId" required maxlength="100"></label>
        <label>
          情报频道
          <select v-model="form.channel" required>
            <option value="" disabled>请选择</option>
            <option value="BOTH">数字化与安全</option>
            <option value="DIGITAL">数字化</option>
            <option value="SAFETY">安全</option>
          </select>
        </label>
        <label>
          来源类型
          <select v-model="form.sourceType" required>
            <option value="" disabled>请选择</option>
            <option value="government">政府</option>
            <option value="standards">标准平台</option>
            <option value="research_institute">科研机构</option>
            <option value="association">协会</option>
            <option value="journal">期刊</option>
            <option value="enterprise">企业</option>
            <option value="media">媒体</option>
            <option value="academic_api">学术 API</option>
            <option value="academic_database">学术数据库</option>
          </select>
        </label>
        <label>
          工程行业
          <select v-model="form.industry" required>
            <option value="" disabled>请选择；无法判断时选 UNKNOWN</option>
            <option v-for="value in ['HIGHWAY', 'BRIDGE', 'TUNNEL', 'RAILWAY', 'RAIL_TRANSIT', 'GENERAL_TRANSPORT', 'UNKNOWN']" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
        <label>
          内容域
          <select v-model="form.contentDomain" required>
            <option value="" disabled>请选择</option>
            <option v-for="value in ['DIGITAL_TRANSFORMATION_CASE', 'RESEARCH_PAPER', 'SOFTWARE_PLATFORM', 'IOT_EQUIPMENT', 'LOW_ALTITUDE_EQUIPMENT', 'AI_APPLICATION', 'SAFETY_REGULATION', 'STANDARD_GUIDANCE', 'ACCIDENT_INVESTIGATION', 'OFFICIAL_NOTICE', 'PENALTY', 'RECTIFICATION', 'UNKNOWN']" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
        <label>
          声明角色
          <select v-model="form.sourceRole" required>
            <option value="" disabled>请选择；该字段不替代事实证据</option>
            <option v-for="value in ['OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY', 'STANDARDS_PUBLISHER', 'RESEARCH_PUBLISHER', 'MANUFACTURER', 'INDEPENDENT_REPORTER', 'AGGREGATOR', 'UNKNOWN']" :key="value" :value="value">{{ value }}</option>
          </select>
        </label>
        <div class="field-grid">
          <label>国家代码<input v-model.trim="form.countryCode" required maxlength="2" placeholder="CN"></label>
          <label>地区代码<input v-model.trim="form.regionCode" required maxlength="20" placeholder="CN-SC"></label>
        </div>
        <label>语言标签<input v-model.trim="form.languageTag" required maxlength="35" placeholder="zh-CN"></label>
        <label>
          预期连接器
          <select v-model="form.collectionMethod" required>
            <option value="" disabled>请选择</option>
            <option value="RSS_ATOM">RSS / Atom</option>
            <option value="JSON_API">JSON API</option>
            <option value="SITEMAP">Sitemap</option>
            <option value="LIST_DETAIL">列表 / 详情</option>
            <option value="DIRECT_PDF">PDF</option>
            <option value="MANUAL_IMPORT">人工 URL / 文件导入</option>
          </select>
        </label>
        <div class="field-grid">
          <label>治理优先级<select v-model="form.priority" required><option value="" disabled>请选择</option><option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option></select></label>
          <label>登记期检查周期（分钟）<input v-model.number="form.pollIntervalMinutes" required type="number" min="1" max="10080"></label>
        </div>
        <p v-if="formError" class="problem" role="alert">{{ formError }}</p>
      </form>
      <template #footer>
        <div class="drawer-actions">
          <button class="secondary-button" type="button" @click="drawerOpen = false">取消</button>
          <button class="primary-button" type="submit" form="source-create-form" :disabled="submitting">
            {{ submitting ? '正在登记…' : '登记为候选' }}
          </button>
        </div>
      </template>
    </ResponsiveDrawer>
  </section>
</template>

<style scoped>
.source-registry-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.source-filters {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.source-filters label,
.source-form label {
  display: grid;
  gap: var(--spacing-1);
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.source-filters select,
.source-form input,
.source-form select {
  width: 100%;
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.source-list {
  display: grid;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.source-row {
  display: grid;
  grid-template-columns: minmax(18rem, 1.4fr) minmax(14rem, 1fr) auto;
  align-items: center;
  gap: var(--spacing-5);
  padding: var(--spacing-4) var(--spacing-5);
  text-decoration: none;
  border-bottom: 1px solid var(--color-border);
}

.source-row:last-child { border-bottom: 0; }
.source-row:hover { background: var(--color-surfaceMuted); }

.source-row__identity,
.source-row__dimensions,
.source-row__status {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.source-row__identity > span:last-child {
  overflow: hidden;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-row__dimensions {
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.source-row__status { justify-content: flex-end; }

.source-code {
  color: var(--color-brand-700);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
}

.source-form { display: grid; gap: var(--spacing-4); }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-3); }
.drawer-actions { display: flex; justify-content: flex-end; gap: var(--spacing-2); }

.primary-button,
.secondary-button {
  display: inline-flex;
  min-height: var(--spacing-10);
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2) var(--spacing-4);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.primary-button { color: var(--color-surface); background: var(--color-brand-700); }
.secondary-button { color: var(--color-brand-700); background: var(--color-surface); }
.primary-button:disabled { cursor: wait; opacity: 0.6; }
.problem { margin: 0; padding: var(--spacing-3); color: var(--color-conflict-700); background: var(--color-conflict-50); border: 1px solid currentColor; border-radius: var(--radius-sm); }
.loading { padding: var(--spacing-8); color: var(--color-ink-600); text-align: center; }

@media (max-width: 70rem) {
  .source-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .source-row { grid-template-columns: 1fr auto; }
  .source-row__dimensions { grid-column: 1 / -1; }
}

@media (max-width: 45rem) {
  .source-filters,
  .source-row,
  .field-grid { grid-template-columns: 1fr; }
  .source-row__status { justify-content: flex-start; }
}
</style>
