<script setup lang="ts">
import type { EventFullProjectionV2 } from '@srbg/contracts'

withDefaults(defineProps<{
  originalUrl: string
  attachments?: EventFullProjectionV2['attachments']
}>(), {
  attachments: () => [],
})
</script>

<template>
  <section class="reader-actions" data-reader-area="actions" aria-labelledby="reader-actions-title">
    <h2 id="reader-actions-title">阅读与材料</h2>
    <a class="reader-actions__primary" :href="originalUrl" target="_blank" rel="noopener noreferrer">查看原文</a>
    <ul v-if="attachments.length" class="reader-actions__list" aria-label="附件材料">
      <li v-for="attachment in attachments" :key="`${attachment.media_id ?? 'source'}:${attachment.name}`">
        <a
          v-if="attachment.redistribution_allowed && attachment.download_url"
          :href="attachment.download_url"
        >下载{{ attachment.name }}</a>
        <a
          v-else
          :href="attachment.source_url"
          target="_blank"
          rel="noopener noreferrer"
        >在原站查看{{ attachment.name }}</a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.reader-actions {
  grid-area: actions;
  display: grid;
  min-width: 0;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.reader-actions h2,
.reader-actions__list {
  margin: 0;
}

.reader-actions h2 {
  color: var(--color-ink-900);
  font-size: var(--text-base);
}

.reader-actions a {
  overflow-wrap: anywhere;
}

.reader-actions__primary {
  display: inline-flex;
  width: fit-content;
  min-height: var(--spacing-10);
  align-items: center;
  padding-inline: var(--spacing-4);
  color: var(--color-surface);
  font-weight: var(--font-weight-semibold);
  background: var(--color-brand-700);
  border-radius: var(--radius-md);
}

.reader-actions__list {
  display: grid;
  gap: var(--spacing-2);
  padding-left: var(--spacing-5);
}
</style>
