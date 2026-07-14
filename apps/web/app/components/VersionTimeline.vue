<script setup lang="ts">
import type { VersionTimelineResponse } from '@srbg/contracts'

defineProps<{ timeline: VersionTimelineResponse }>()

const changeLabels = {
  INITIAL: '初始版本',
  METADATA_ONLY: '元数据变化',
  CONTENT_UPDATE: '实质变化',
  CORRECTION: '更正',
  AMENDMENT: '修订',
  REPLACEMENT: '替代',
  WITHDRAWAL: '撤回',
} as const
</script>

<template>
  <section class="version-timeline" aria-labelledby="version-timeline-title">
    <h3 id="version-timeline-title">版本时间线</h3>
    <ol>
      <li v-for="entry in timeline.versions" :key="entry.version_id" :data-current="entry.is_current">
        <span aria-hidden="true" />
        <div>
          <strong>v{{ entry.version_number }} · {{ changeLabels[entry.change_type] }}</strong>
          <p>{{ entry.processing_state }} · {{ entry.review_state }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.version-timeline h3 { margin-bottom: var(--spacing-3); }
.version-timeline ol { display: grid; margin: 0; padding: 0; list-style: none; gap: var(--spacing-3); }
.version-timeline li { display: grid; grid-template-columns: auto 1fr; gap: var(--spacing-3); }
.version-timeline li > span { width: var(--spacing-2); height: var(--spacing-2); margin-top: var(--spacing-2); background: var(--color-borderStrong); border-radius: var(--radius-pill); }
.version-timeline li[data-current='true'] > span { background: var(--color-brand-600); }
.version-timeline p { margin: var(--spacing-1) 0 0; color: var(--color-ink-500); font-size: var(--text-xs); }
</style>
