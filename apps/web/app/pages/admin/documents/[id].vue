<script setup lang="ts">
import type { DocumentDetail } from '@srbg/contracts'
import { PageHeader, StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

const route = useRoute()
const documentId = computed(() => String(route.params.id))
const { data: document, error } = await useFetch<DocumentDetail>(
  () => `/api/v1/admin/documents/${documentId.value}`,
  { retry: 0, timeout: 5_000 },
)

const shanghaiTime = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})

function formatTime(value: string): string {
  return shanghaiTime.format(new Date(value))
}

function formatBytes(value: number): string {
  if (value < 1_024) return `${value} B`
  if (value < 1_024 * 1_024) return `${(value / 1_024).toFixed(1)} KiB`
  return `${(value / (1_024 * 1_024)).toFixed(1)} MiB`
}
</script>

<template>
  <section v-if="document" class="document-page">
    <PageHeader
      :title="document.current_version.title ?? document.current_version.original_filename"
      eyebrow="不可变原始文档"
      :description="document.canonical_url"
      :updated-at="document.current_version.acquired_at"
      updated-label="采集时间"
    >
      <template #status>
        <StatusBadge tone="healthy" label="扫描通过" />
        <StatusBadge tone="verified" :label="`SHA-256 · ${document.raw_object.sha256.slice(0, 12)}…`" />
      </template>
      <template #actions>
        <NuxtLink class="secondary-button" :to="`/admin/sources/${document.source_id}`">返回来源</NuxtLink>
        <a class="primary-button" :href="document.canonical_url" target="_blank" rel="noopener noreferrer">打开原文</a>
      </template>
    </PageHeader>

    <div class="evidence-banner">
      此页面只预览服务端提取的元数据，不在浏览器内渲染不可信 HTML/PDF，也不公开原始对象地址。
    </div>

    <div class="metadata-grid">
      <article class="panel">
        <h2>文档版本</h2>
        <dl>
          <div><dt>文档 ID</dt><dd>{{ document.id }}</dd></div>
          <div><dt>来源</dt><dd>{{ document.source_name }}</dd></div>
          <div><dt>文档类型</dt><dd>{{ document.document_kind }}</dd></div>
          <div><dt>版本号</dt><dd>v{{ document.current_version.version_number }}</dd></div>
          <div><dt>首次发现</dt><dd>{{ formatTime(document.first_discovered_at) }}</dd></div>
          <div><dt>原始文件名</dt><dd>{{ document.current_version.original_filename }}</dd></div>
          <div><dt>内容哈希</dt><dd>{{ document.current_version.content_hash }}</dd></div>
        </dl>
      </article>
      <article class="panel">
        <h2>原始对象</h2>
        <dl>
          <div><dt>对象 ID</dt><dd>{{ document.raw_object.id }}</dd></div>
          <div><dt>MIME</dt><dd>{{ document.raw_object.detected_mime }}</dd></div>
          <div><dt>大小</dt><dd>{{ formatBytes(document.raw_object.byte_size) }}</dd></div>
          <div><dt>扫描状态</dt><dd>{{ document.raw_object.scan_status }}</dd></div>
          <div><dt>SHA-256</dt><dd>{{ document.raw_object.sha256 }}</dd></div>
        </dl>
      </article>
    </div>
  </section>

  <section v-else class="document-page">
    <PageHeader title="文档元数据" eyebrow="原始文档库" description="正在读取不可变版本记录。" />
    <p v-if="error" class="problem" role="alert">文档不存在或服务暂不可用。</p>
  </section>
</template>

<style scoped>
.document-page { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.evidence-banner { padding: var(--spacing-3) var(--spacing-4); color: var(--color-brand-800); background: var(--color-brand-50); border-left: var(--spacing-1) solid var(--color-brand-600); border-radius: var(--radius-sm); }
.metadata-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: var(--spacing-4); }
.panel { padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.panel h2 { margin: 0 0 var(--spacing-4); font-size: var(--text-lg); }
.panel dl { display: grid; margin: 0; }
.panel dl div { display: grid; grid-template-columns: minmax(7rem, 0.55fr) 1.45fr; gap: var(--spacing-3); padding: var(--spacing-3) 0; border-top: 1px solid var(--color-border); }
dt { color: var(--color-ink-600); }
dd { margin: 0; font-family: var(--font-mono); overflow-wrap: anywhere; }
.primary-button,
.secondary-button { display: inline-flex; min-height: var(--spacing-10); align-items: center; padding: var(--spacing-2) var(--spacing-4); font-weight: var(--font-weight-semibold); text-decoration: none; border: 1px solid var(--color-brand-700); border-radius: var(--radius-sm); }
.primary-button { color: var(--color-surface); background: var(--color-brand-700); }
.secondary-button { color: var(--color-brand-700); background: var(--color-surface); }
.problem { margin: 0; padding: var(--spacing-3); color: var(--color-conflict-700); background: var(--color-conflict-50); border: 1px solid currentColor; border-radius: var(--radius-sm); }

@media (max-width: 52rem) { .metadata-grid { grid-template-columns: 1fr; } }
@media (max-width: 36rem) { .panel dl div { grid-template-columns: 1fr; gap: var(--spacing-1); } }
</style>
