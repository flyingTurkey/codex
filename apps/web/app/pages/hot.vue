<script setup lang="ts">
import type { HotTopicPage, ProblemDetails } from '@srbg/contracts'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

const window = ref<'7d' | '14d' | '30d'>('7d')
const { data, error, refresh, status } = await useFetch<HotTopicPage>('/api/v1/hot-topics', {
  query: { window },
  retry: 0,
  server: false,
  timeout: 5_000,
})

const problem = computed<ProblemDetails | null>(() => error.value?.data as ProblemDetails ?? null)
const shanghaiDate = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})
</script>

<template>
  <section class="hot-page">
    <PageHeader
      title="行业热点"
      eyebrow="独立信源与事件活跃度"
      description="热点只反映关注变化，不提高事实置信度；同一通稿的转载只计为一个来源链。"
    >
      <template #status>
        <StatusBadge tone="pending" label="内测评估 / 自动合并关闭" />
      </template>
    </PageHeader>

    <label class="hot-page__window">
      时间窗口
      <select v-model="window">
        <option value="7d">最近 7 天</option>
        <option value="14d">最近 14 天</option>
        <option value="30d">最近 30 天</option>
      </select>
    </label>

    <Skeleton v-if="status === 'idle' || status === 'pending'" :lines="6" label="正在计算热点" />
    <ProblemNotice v-else-if="problem" :problem="problem" @retry="refresh" />
    <ol v-else-if="data?.items.length" class="hot-page__list">
      <li v-for="topic in data.items" :key="topic.id">
        <div>
          <span>{{ topic.domain === 'SAFETY' ? '安全' : '数字化' }}</span>
          <h2>{{ topic.title }}</h2>
          <p>最近活动：{{ shanghaiDate.format(new Date(topic.latest_activity_at)) }}</p>
        </div>
        <dl>
          <div><dt>热度</dt><dd>{{ topic.heat_score }}</dd></div>
          <div><dt>事件</dt><dd>{{ topic.event_count }}</dd></div>
          <div><dt>独立信源</dt><dd>{{ topic.independent_source_count }}</dd></div>
        </dl>
      </li>
    </ol>
    <EmptyState
      v-else
      title="当前窗口暂无已确认热点"
      description="主题须经过人工确认，并具有已发布事件后才会出现。"
      icon="EmptyPage"
    />
  </section>
</template>

<style scoped>
.hot-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.hot-page__window {
  display: grid;
  width: min(100%, 16rem);
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  gap: var(--spacing-2);
}

.hot-page__window select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.hot-page__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-3);
}

.hot-page__list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-5);
}

.hot-page__list h2,
.hot-page__list p,
.hot-page__list dl {
  margin: 0;
}

.hot-page__list span,
.hot-page__list p,
.hot-page__list dt {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.hot-page__list dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(4rem, auto));
  gap: var(--spacing-4);
}

.hot-page__list dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-brand-700);
  font-size: var(--text-xl);
  font-weight: var(--font-weight-bold);
}

@media (max-width: 47.999rem) {
  .hot-page__list li {
    grid-template-columns: 1fr;
    padding: var(--spacing-4);
  }
}
</style>
