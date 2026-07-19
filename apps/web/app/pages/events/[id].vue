<script setup lang="ts">
import type { EventAppendixV2, EventFullProjectionV2, EventMetadataProjectionV2, ProblemDetails } from '@srbg/contracts'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'

type EventProjection = EventFullProjectionV2 | EventMetadataProjectionV2
const route = useRoute()
const eventId = String(route.params.id)
const result = await useFetch<EventProjection>(`/api/v2/events/${eventId}`, {
  key: `event-v2:${eventId}`, server: false, retry: 0, timeout: 5_000,
})
const detail = computed(() => result.data.value)
const full = computed(() => detail.value?.projection_kind === 'FULL' ? detail.value : null)
const appendixOpen = ref(false)
const appendix = ref<EventAppendixV2 | null>(null)
const appendixLoading = ref(false)
const problem = computed(() => result.error.value?.data as ProblemDetails ?? null)
const shanghai = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short', timeZone: 'Asia/Shanghai' })
function formatDate(value: string | null | undefined): string { return value ? shanghai.format(new Date(value)) : '原文未提供' }
async function toggleAppendix(): Promise<void> {
  appendixOpen.value = !appendixOpen.value
  if (!appendixOpen.value || appendix.value) return
  appendixLoading.value = true
  try { appendix.value = await $fetch<EventAppendixV2>(`/api/v2/events/${eventId}/appendix`) }
  finally { appendixLoading.value = false }
}
</script>

<template>
  <section class="reader-page">
    <PageHeader :title="detail?.title ?? '情报阅读'" eyebrow="土木工程情报阅读页" />
    <Skeleton v-if="result.status.value === 'idle' || result.status.value === 'pending'" :lines="8" label="正在加载情报" />
    <ProblemNotice v-else-if="problem" :problem="problem" @retry="result.refresh" />
    <template v-else-if="detail">
      <aside v-if="full?.correction_alert" class="reader-page__correction" role="alert">{{ full.correction_alert }}</aside>
      <dl class="reader-page__meta">
        <div><dt>来源</dt><dd>{{ full?.source.name ?? (detail.projection_kind === 'R3_METADATA' ? detail.source_name : '') }}</dd></div>
        <div><dt>原文发布时间</dt><dd>{{ formatDate(detail.source_published_at) }}</dd></div>
        <div><dt>首次发现时间</dt><dd>{{ formatDate(detail.first_discovered_at) }}</dd></div>
        <div><dt>主类型</dt><dd>{{ detail.primary_type }}</dd></div>
      </dl>
      <aside v-if="detail.projection_kind === 'R3_METADATA'" class="reader-page__pending">
        <StatusBadge tone="pending" label="待 Owner 审核" />
        <p>当前为 R3 元数据投影，正文、证据、媒体和 AI 内容尚未向普通阅读面开放。</p>
      </aside>
      <template v-if="full">
        <article class="reader-page__section"><h2>原文摘录</h2><blockquote>{{ full.source_excerpt.text }}</blockquote></article>
        <article class="reader-page__section">
          <h2>AI 总结 <StatusBadge :tone="full.ai_summary.status === 'SUCCEEDED' ? 'info' : 'pending'" :label="full.ai_summary.status" /></h2>
          <p v-if="full.ai_summary.body" class="reader-page__summary">{{ full.ai_summary.body }}</p>
          <p v-else>AI 总结暂不可用；已通过门禁的原文摘录仍可阅读，系统将在恢复后补齐。</p>
        </article>
        <section v-if="full.media?.length" class="reader-page__section"><h2>图片</h2><img v-for="media in full.media" :key="media.media_id" :src="media.preview_url ?? ''" :alt="media.name"></section>
        <section v-if="full.attachments?.length" class="reader-page__section"><h2>附件</h2><ul><li v-for="file in full.attachments" :key="file.name"><a :href="file.download_url ?? file.source_url">{{ file.name }}</a></li></ul></section>
      </template>
      <p><a :href="detail.original_url" target="_blank" rel="noopener noreferrer">查看原文</a></p>
      <section v-if="full" class="reader-page__appendix">
        <button type="button" :aria-expanded="appendixOpen" @click="toggleAppendix">{{ appendixOpen ? '收起' : '展开' }}证据、关系、更正与自动处理附录</button>
        <Skeleton v-if="appendixLoading" :lines="3" label="正在加载附录" />
        <div v-else-if="appendixOpen && appendix"><p>Accepted claims：{{ appendix.claims?.length ?? 0 }}</p><p>证据：{{ appendix.evidence?.length ?? 0 }}</p><p>关系：{{ appendix.relationships?.length ?? 0 }}</p><p>更正：{{ appendix.corrections?.length ?? 0 }}</p></div>
      </section>
    </template>
    <EmptyState v-else title="情报不可见" description="该内容未通过普通阅读投影门禁。" />
  </section>
</template>

<style scoped>
.reader-page { display:grid; width:min(100%,var(--srbg-layout-reader-max)); margin-inline:auto; gap:var(--spacing-5); }
.reader-page__meta { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--spacing-3); }
.reader-page__meta div,.reader-page__section,.reader-page__pending,.reader-page__appendix { padding:var(--spacing-4); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); }
.reader-page__meta dt { color:var(--color-ink-600); font-size:var(--text-xs); }.reader-page__meta dd { margin:var(--spacing-1) 0 0; }
.reader-page__section h2 { display:flex; align-items:center; gap:var(--spacing-2); }.reader-page__summary { white-space:pre-line; line-height:1.8; }
.reader-page__correction { padding:var(--spacing-3); border:1px solid var(--color-borderStrong); border-radius:var(--radius-sm); }
@media(max-width:47.999rem){.reader-page__meta{grid-template-columns:1fr}}
</style>
