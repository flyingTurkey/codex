<script setup lang="ts">
import type { DocumentPageView, EvidenceView } from '@srbg/contracts'
import { computed, ref } from 'vue'

const props = defineProps<{ page: DocumentPageView, evidence: EvidenceView[] }>()
const emit = defineEmits<{ page: [pageNumber: number] }>()
const zoom = ref(1)

const pageEvidence = computed(() => props.evidence.filter((entry) => {
  const locator = entry.locator
  return locator?.type !== 'HTML_PARAGRAPH' && locator?.page_number === props.page.page_number
}))

function highlightStyle(entry: EvidenceView): string {
  const locator = entry.locator
  if (!locator || locator.type === 'HTML_PARAGRAPH') return ''
  const { bbox } = locator
  return [
    `left: ${(bbox.x0 / props.page.width_mpt * 100).toFixed(4)}%`,
    `top: ${(bbox.y0 / props.page.height_mpt * 100).toFixed(4)}%`,
    `width: ${((bbox.x1 - bbox.x0) / props.page.width_mpt * 100).toFixed(4)}%`,
    `height: ${((bbox.y1 - bbox.y0) / props.page.height_mpt * 100).toFixed(4)}%`,
  ].join('; ')
}

function changePage(value: number): void {
  if (value >= 1 && value <= props.page.page_count) emit('page', value)
}
</script>

<template>
  <section class="pdf-evidence" aria-labelledby="pdf-evidence-title">
    <header>
      <div>
        <h3 id="pdf-evidence-title">PDF 页码证据</h3>
        <p>第 {{ page.page_number }} / {{ page.page_count }} 页 · {{ page.text_source === 'OCR' ? 'OCR 识别' : '原生文本' }}</p>
      </div>
      <div class="pdf-evidence__zoom" aria-label="预览缩放">
        <button type="button" aria-label="缩小" @click="zoom = Math.max(0.75, zoom - 0.25)">−</button>
        <output>{{ Math.round(zoom * 100) }}%</output>
        <button type="button" aria-label="放大" @click="zoom = Math.min(2, zoom + 0.25)">+</button>
      </div>
    </header>
    <div class="pdf-evidence__viewport">
      <div class="pdf-evidence__page" :style="{ width: `${zoom * 100}%` }">
        <img :src="page.preview_url" :alt="`PDF 第 ${page.page_number} 页安全预览`">
        <mark
          v-for="entry in pageEvidence"
          :key="entry.id"
          data-testid="pdf-highlight"
          :style="highlightStyle(entry)"
        ><span class="sr-only">高亮证据：{{ entry.excerpt }}</span></mark>
      </div>
    </div>
    <nav aria-label="PDF 页码">
      <button type="button" aria-label="上一页" :disabled="page.page_number <= 1" @click="changePage(page.page_number - 1)">上一页</button>
      <label>
        跳转页码
        <select :value="page.page_number" @change="changePage(Number(($event.target as HTMLSelectElement).value))">
          <option v-for="number in page.page_count" :key="number" :value="number">{{ number }}</option>
        </select>
      </label>
      <button type="button" aria-label="下一页" :disabled="page.page_number >= page.page_count" @click="changePage(page.page_number + 1)">下一页</button>
    </nav>
  </section>
</template>

<style scoped>
.pdf-evidence, .pdf-evidence header, .pdf-evidence nav, .pdf-evidence__zoom { display: flex; gap: var(--spacing-3); }
.pdf-evidence { flex-direction: column; }
.pdf-evidence header, .pdf-evidence nav { align-items: center; justify-content: space-between; }
.pdf-evidence h3, .pdf-evidence p { margin: 0; }
.pdf-evidence p { color: var(--color-ink-500); font-size: var(--text-xs); }
.pdf-evidence button, .pdf-evidence select { min-height: var(--spacing-9); padding: var(--spacing-2); color: var(--color-ink-700); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.pdf-evidence__viewport { overflow: auto; background: var(--color-surfaceMuted); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.pdf-evidence__page { position: relative; min-width: 100%; margin-inline: auto; }
.pdf-evidence__page img { display: block; width: 100%; height: auto; }
.pdf-evidence__page mark { position: absolute; padding: 0; background: color-mix(in srgb, var(--color-reviewPending-500) 28%, transparent); border: 2px solid var(--color-corporateAccent-500); border-radius: var(--radius-xs); pointer-events: none; }
.pdf-evidence nav label { display: flex; align-items: center; gap: var(--spacing-2); font-size: var(--text-sm); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
