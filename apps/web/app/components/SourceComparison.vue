<script setup lang="ts">
import type { SourceComparison } from '@srbg/contracts'

defineProps<{ comparison: SourceComparison }>()

const roleLabels = {
  ORIGINAL: '原始发布',
  REPRINT: '转载',
  MIRROR: '同机构镜像',
  INDEPENDENT_REPORT: '独立报道',
  VENDOR_STATEMENT: '厂商声明',
  MEDIA_REPORT: '媒体报道',
  INDEPENDENT_VERIFICATION: '独立验证',
} as const
</script>

<template>
  <section class="source-comparison" aria-labelledby="source-comparison-title">
    <header>
      <div>
        <h2 id="source-comparison-title">来源对比</h2>
        <p>共 {{ comparison.independent_source_count }} 个独立信源；转载和镜像按来源链折叠计数。</p>
      </div>
    </header>
    <div class="source-comparison__table" role="region" tabindex="0" aria-label="事件来源对比表">
      <table>
        <thead><tr><th>来源</th><th>关系</th><th>来源链</th><th>已接受事实</th><th>证据</th></tr></thead>
        <tbody>
          <tr v-for="source in comparison.sources" :key="source.item_id">
            <td><a :href="source.original_url" target="_blank" rel="noreferrer">{{ source.source_name }}</a></td>
            <td>{{ roleLabels[source.role] }}</td>
            <td>{{ source.lineage_root }}</td>
            <td>{{ source.accepted_claim_count }}</td>
            <td>{{ source.evidence_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.source-comparison { display: grid; padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); gap: var(--spacing-3); }
.source-comparison h2, .source-comparison p { margin: 0; }
.source-comparison p { color: var(--color-ink-600); font-size: var(--text-sm); }
.source-comparison__table { overflow-x: auto; }
.source-comparison table { width: 100%; border-collapse: collapse; white-space: nowrap; }
.source-comparison th, .source-comparison td { padding: var(--spacing-3); text-align: start; border-bottom: 1px solid var(--color-border); }
.source-comparison th { color: var(--color-ink-600); font-size: var(--text-xs); }
</style>
