<script setup lang="ts">
import type { SourceAutoScoreDetailView, SourceAutoScoreSummaryView } from '@srbg/contracts'

const props = defineProps<{ sourceId: string, summary: SourceAutoScoreSummaryView | null }>()
const detail = ref<SourceAutoScoreDetailView | null>(null)
const loading = ref(false)

const components = computed(() => detail.value ? [
  ['主题相关性', detail.value.topic_relevance_score, 35],
  ['连接器稳定性', detail.value.connector_stability_score, 25],
  ['样本解析完整度', detail.value.sample_completeness_score, 20],
  ['画像证据与置信度', detail.value.profile_evidence_score, 10],
  ['内容有效性与时效', detail.value.content_validity_score, 10],
] as const : [])

async function loadDetail(): Promise<void> {
  if (detail.value || loading.value) return
  loading.value = true
  try {
    detail.value = await $fetch<SourceAutoScoreDetailView>(
      `/api/v1/sources/${props.sourceId}/auto-score`,
      { retry: 0, timeout: 5_000 },
    )
  }
  finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="summary" class="auto-score" role="group" aria-label="自动启用评分">
    <div><strong>自动启用分数 {{ summary.total_score }}/100</strong><span>{{ summary.eligible ? '满足自动启用规则' : '暂不满足自动启用规则' }}</span></div>
    <p v-if="summary.reason_codes.length">原因：{{ summary.reason_codes.join('、') }}</p>
    <button type="button" @click="loadDetail">{{ loading ? '读取中…' : '查看分项解释' }}</button>
    <dl v-if="detail">
      <div v-for="item in components" :key="item[0]"><dt>{{ item[0] }}</dt><dd>{{ item[1] }}/{{ item[2] }}</dd></div>
    </dl>
    <p v-if="detail && Object.values(detail.hard_gate_results).some(value => !value)">硬门禁失败：{{ detail.reason_codes.join('、') }}</p>
    <small>{{ summary.rule_version }}</small>
  </div>
</template>

<style scoped>
.auto-score { display: grid; gap: .5rem; padding: .75rem; border-radius: .5rem; background: var(--ui-bg-muted); }
.auto-score > div { display: flex; justify-content: space-between; gap: 1rem; }
.auto-score p { margin: 0; }
.auto-score dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: .5rem; margin: 0; }
.auto-score dl div { display: grid; gap: .15rem; }
</style>
