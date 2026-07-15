<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import type { FeedContentTypeFilter } from '../composables/useIntelligenceFeed'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const mode = ref<'selected' | 'all'>('all')
const contentType = ref<FeedContentTypeFilter>('DIGITAL_CASE')
const engineeringDomain = ref('all')
const scenario = ref('all')
const maturity = ref('all')
const sourceNature = ref('all')
const paperType = ref('all')
const technologyTag = ref('all')
const accessLevel = ref('all')
const publicationYear = ref('all')
const productKind = ref('all')
const evidenceLevel = ref('all')
const deploymentMode = ref('all')
const sort = ref<'latest' | 'relevance'>('latest')
const filters = computed(() => ({
  engineering_domain: engineeringDomain.value,
  maturity: maturity.value,
  scenario: scenario.value,
  source_nature: sourceNature.value,
  paper_type: paperType.value,
  technology_tag: technologyTag.value,
  access_level: accessLevel.value,
  year: publicationYear.value,
  product_kind: productKind.value,
  evidence_level: evidenceLevel.value,
  deployment_mode: deploymentMode.value,
  sort: contentType.value === 'DIGITAL_CASE' && mode.value === 'selected'
    ? 'relevance' as const
    : sort.value,
}))
const isPaper = computed(() => contentType.value === 'JOURNAL_PAPER')
const productTypes = ['SOFTWARE_PRODUCT', 'IOT_PRODUCT', 'LOW_ALTITUDE_EQUIPMENT', 'AI_EQUIPMENT'] as const
const isProduct = computed(() => productTypes.includes(contentType.value as typeof productTypes[number]))
const viewNoun = computed(() => isProduct.value ? '产品' : isPaper.value ? '论文' : '案例')
const pageCopy = computed(() => isProduct.value
  ? {
      title: '技术产品',
      eyebrow: '软件、物联网、低空与 AI 设备',
      description: '统一展示产品型号、版本、厂商声明、工程证据与许可限制；内容仅供技术调研。',
      status: '产品证据分层已启用',
      emptyTitle: '暂无技术产品',
      emptyDescription: '当前筛选下没有可见产品，可调整类型、场景、证据等级或部署方式。',
    }
  : isPaper.value
  ? {
      title: '期刊论文',
      eyebrow: '开放学术元数据',
      description: '检索工程论文题录，区分元数据、获准摘要和开放原文，并保留研究条件与局限。',
      status: '版权边界已启用',
      emptyTitle: '暂无期刊论文',
      emptyDescription: '当前筛选下没有可见论文，可调整专业、技术、年份或开放状态。',
    }
  : {
      title: '数字化案例',
      eyebrow: '工程行业数字化转型',
      description: '从全国案例中辨认已经落地的工程场景，并把发布方成效与独立验证分开。',
      status: '相关性 v1 已启用',
      emptyTitle: '暂无数字化情报',
      emptyDescription: '当前筛选下没有可见案例，可调整专业、场景或成熟度。',
    })
const { data: feed, status, error, refresh } = await useIntelligenceFeed(
  mode,
  'digital',
  contentType,
  filters,
)

function selectMode(next: 'selected' | 'all'): void {
  mode.value = next
  sort.value = next === 'selected' && contentType.value === 'DIGITAL_CASE' ? 'relevance' : 'latest'
}

watch(contentType, () => {
  mode.value = 'all'
  sort.value = 'latest'
})
</script>

<template>
  <IntelligenceFeedPage
    v-model:content-type="contentType"
    v-model:engineering-domain="engineeringDomain"
    v-model:scenario="scenario"
    v-model:maturity="maturity"
    v-model:source-nature="sourceNature"
    v-model:paper-type="paperType"
    v-model:technology-tag="technologyTag"
    v-model:access-level="accessLevel"
    v-model:publication-year="publicationYear"
    v-model:product-kind="productKind"
    v-model:evidence-level="evidenceLevel"
    v-model:deployment-mode="deploymentMode"
    :title="pageCopy.title"
    :eyebrow="pageCopy.eyebrow"
    :description="pageCopy.description"
    :status-label="pageCopy.status"
    status-tone="verified"
    :empty-title="pageCopy.emptyTitle"
    :empty-description="pageCopy.emptyDescription"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :problem="error?.data"
    initial-domain="digital"
    :content-type-options="[
      { label: '数字化案例', value: 'DIGITAL_CASE' },
      { label: '期刊论文', value: 'JOURNAL_PAPER' },
      { label: '软件产品', value: 'SOFTWARE_PRODUCT' },
      { label: '物联网产品', value: 'IOT_PRODUCT' },
      { label: '低空设备', value: 'LOW_ALTITUDE_EQUIPMENT' },
      { label: 'AI 设备', value: 'AI_EQUIPMENT' },
    ]"
    :show-domain-filter="false"
    show-filters
    :show-digital-filters="contentType === 'DIGITAL_CASE'"
    :show-paper-filters="contentType === 'JOURNAL_PAPER'"
    :show-product-filters="isProduct"
    @retry="refresh"
  >
    <template #actions>
      <div class="digital-page__actions" :aria-label="`${viewNoun}视图与排序`">
        <button type="button" :aria-pressed="mode === 'all'" @click="selectMode('all')">
          全部{{ viewNoun }}
        </button>
        <button type="button" :aria-pressed="mode === 'selected'" @click="selectMode('selected')">
          精选{{ viewNoun }}
        </button>
        <label>
          排序
          <select v-model="sort" :disabled="mode === 'selected'">
            <option value="latest">最新发现</option>
            <option v-if="contentType === 'DIGITAL_CASE'" value="relevance">相关性 v1</option>
          </select>
        </label>
      </div>
    </template>
  </IntelligenceFeedPage>
</template>

<style scoped>
.digital-page__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: var(--spacing-2);
}

.digital-page__actions button,
.digital-page__actions select {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.digital-page__actions button[aria-pressed='true'] {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.digital-page__actions label {
  display: grid;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}
</style>
