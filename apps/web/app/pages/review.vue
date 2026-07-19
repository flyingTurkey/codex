<script setup lang="ts">
import { EmptyState, PageHeader, Skeleton, StatusBadge } from '@srbg/ui'

interface ReviewCase {
  case_id: string
  reason: string
  risk_tier: 'R1' | 'R2' | 'R3' | 'R4'
  safe_metadata: { title?: string, source_name?: string, original_url?: string }
  state: string
  version: number
}

const { data: cases, status, refresh } = await useFetch<ReviewCase[]>('/api/v2/review/cases', {
  server: false, default: () => [], retry: 0, timeout: 5_000,
})
</script>

<template>
  <section class="review-page">
    <PageHeader title="Owner 复核" eyebrow="分类、证据与 AI 解读独立决策" description="低置信、主类并列、R3 与 R4 内容不会进入普通 Feed。" />
    <Skeleton v-if="status === 'idle' || status === 'pending'" :lines="5" label="正在加载复核案例" />
    <ol v-else-if="cases?.length" class="review-page__list">
      <li v-for="item in cases" :key="item.case_id">
        <div><StatusBadge :tone="item.risk_tier === 'R4' ? 'conflict' : 'pending'" :label="item.risk_tier" /><span>{{ item.reason }}</span></div>
        <h2>{{ item.safe_metadata.title ?? '安全元数据待补充' }}</h2>
        <p>{{ item.safe_metadata.source_name ?? '来源待确认' }} · 版本 {{ item.version }}</p>
        <a v-if="item.safe_metadata.original_url && item.risk_tier !== 'R4'" :href="item.safe_metadata.original_url" target="_blank" rel="noopener noreferrer">查看原站</a>
      </li>
    </ol>
    <EmptyState v-else title="没有待复核案例" description="分类门禁和证据门禁当前没有需要 Owner 决策的内容。" />
    <button type="button" @click="() => refresh()">刷新</button>
  </section>
</template>

<style scoped>
.review-page { display:grid; width:min(100%,var(--srbg-layout-content-max)); margin-inline:auto; gap:var(--spacing-5); }
.review-page__list { display:grid; padding:0; list-style:none; gap:var(--spacing-3); }
.review-page__list li { padding:var(--spacing-4); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); }
.review-page__list li>div { display:flex; align-items:center; gap:var(--spacing-2); }
</style>
