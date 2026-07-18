<script setup lang="ts">
import type { ClusterCandidateView, ProblemDetails } from '@srbg/contracts'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

const kind = ref<'DUPLICATE' | 'EVENT' | 'TOPIC' | 'RELATION'>('DUPLICATE')
const selected = ref<ClusterCandidateView | null>(null)
const { data, error, refresh, status } = await useFetch<ClusterCandidateView[]>(
  '/api/v1/admin/clustering-workbench',
  { query: { kind, status: 'PENDING_REVIEW' }, retry: 0, server: false, timeout: 5_000 },
)
const problem = computed<ProblemDetails | null>(() => error.value?.data as ProblemDetails ?? null)

</script>

<template>
  <section class="cluster-page">
    <PageHeader
      title="旧聚类只读历史"
      eyebrow="PERS-08 自动关系"
      description="PERS-08 已停止关系人工候选；旧表和旧 API 仅作为只读历史保留。"
    >
      <template #status><StatusBadge tone="info" label="自动关系已启用" /></template>
    </PageHeader>
    <label class="cluster-page__kind">
      候选类型
      <select v-model="kind" @change="selected = null">
        <option value="DUPLICATE">重复候选</option>
        <option value="EVENT">事件候选</option>
        <option value="TOPIC">主题候选</option>
        <option value="RELATION">后续关系</option>
      </select>
    </label>

    <Skeleton v-if="status === 'idle' || status === 'pending'" :lines="6" label="正在加载聚类候选" />
    <ProblemNotice v-else-if="problem" :problem="problem" @retry="refresh" />
    <div v-else-if="data?.length" class="cluster-page__layout">
      <ol class="cluster-page__list">
        <li v-for="candidate in data" :key="candidate.id">
          <button type="button" @click="selected = candidate">
            <strong>{{ candidate.kind }} · {{ candidate.score_bps == null ? '关系候选' : `${candidate.score_bps / 100}%` }}</strong>
            <span>{{ candidate.member_ids.length }} 个成员</span>
            <span v-if="candidate.hard_conflicts.length" class="is-conflict">
              禁止合并：{{ candidate.hard_conflicts.join('、') }}
            </span>
          </button>
        </li>
      </ol>
      <section v-if="selected" class="cluster-page__decision">
        <h2>只读历史</h2>
        <ul><li v-for="member in selected.member_ids" :key="member">{{ member }}</li></ul>
        <ul><li v-for="feature in selected.feature_explanations" :key="feature">{{ feature }}</li></ul>
        <p>自动决定及个人纠正请在对应事件详情页查看和操作。</p>
      </section>
    </div>
    <EmptyState v-else title="没有待处理候选" description="当前类型的人工审核队列为空。" icon="EmptyPage" />
  </section>
</template>

<style scoped>
.cluster-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}
.cluster-page__kind { display: grid; width: min(100%, 18rem); gap: var(--spacing-2); }
.cluster-page__kind select,
.cluster-page__decision textarea { padding: var(--spacing-2); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.cluster-page__layout { display: grid; grid-template-columns: minmax(18rem, 2fr) minmax(20rem, 3fr); gap: var(--spacing-4); }
.cluster-page__list { display: grid; margin: 0; padding: 0; list-style: none; gap: var(--spacing-2); }
.cluster-page__list button { display: grid; width: 100%; padding: var(--spacing-4); text-align: start; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); cursor: pointer; gap: var(--spacing-1); }
.cluster-page__list span { color: var(--color-ink-600); font-size: var(--text-sm); }
.cluster-page__list .is-conflict { color: var(--color-conflict-700); }
.cluster-page__decision { display: grid; padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); gap: var(--spacing-3); align-content: start; }
.cluster-page__decision h2, .cluster-page__decision ul, .cluster-page__decision p { margin: 0; }
.cluster-page__decision label { display: grid; gap: var(--spacing-2); }
.cluster-page__decision textarea { min-height: 8rem; resize: vertical; }
.cluster-page__decision div { display: flex; flex-wrap: wrap; gap: var(--spacing-2); }
.cluster-page__decision button { padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); cursor: pointer; }
@media (max-width: 63.999rem) { .cluster-page__layout { grid-template-columns: 1fr; } }
</style>
