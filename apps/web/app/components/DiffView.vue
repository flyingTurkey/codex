<script setup lang="ts">
import type { VersionDiffResponse } from '@srbg/contracts'

defineProps<{ diff: VersionDiffResponse }>()
</script>

<template>
  <section class="diff-view" aria-labelledby="diff-view-title">
    <h3 id="diff-view-title">版本差异</h3>
    <p>{{ diff.material ? '实质变化，必须重新复核' : '非实质变化' }} · 变化 {{ diff.changed_token_count }} 词</p>
    <ul v-if="diff.critical_fields.length" aria-label="关键字段变化">
      <li v-for="field in diff.critical_fields" :key="field.field">
        <strong>{{ field.field }}</strong><del>{{ field.before ?? '无' }}</del><ins>{{ field.after ?? '无' }}</ins>
      </li>
    </ul>
    <ol>
      <li v-for="page in diff.pages" :key="`${page.page_number}-${page.category}`">
        <strong>第 {{ page.page_number }} 页 · {{ page.category }}</strong>
        <p v-for="(hunk, index) in page.hunks" :key="index" :data-operation="hunk.operation">
          <del v-if="hunk.before">{{ hunk.before }}</del><ins v-if="hunk.after">{{ hunk.after }}</ins>
        </p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.diff-view { display: grid; gap: var(--spacing-3); }
.diff-view h3, .diff-view p { margin: 0; }
.diff-view ul, .diff-view ol { display: grid; margin: 0; padding: 0; list-style: none; gap: var(--spacing-3); }
.diff-view li { display: grid; gap: var(--spacing-2); padding: var(--spacing-3); background: var(--color-surfaceMuted); border-radius: var(--radius-sm); }
.diff-view del, .diff-view ins { display: block; padding: var(--spacing-1) var(--spacing-2); text-decoration: none; border-radius: var(--radius-xs); }
.diff-view del::before { content: '删除：'; font-weight: var(--font-weight-semibold); }
.diff-view ins::before { content: '新增：'; font-weight: var(--font-weight-semibold); }
.diff-view del { color: var(--color-conflict-700); background: var(--color-conflict-50); }
.diff-view ins { color: var(--color-verified-700); background: var(--color-verified-50); }
</style>
