<script setup lang="ts">
import type {
  ClaimView,
  DocumentPageView,
  EvidenceView,
  VersionDiffResponse,
  VersionTimelineResponse,
} from '@srbg/contracts'
import { ResponsiveDrawer } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import DiffView from './DiffView.vue'
import PdfEvidenceViewer from './PdfEvidenceViewer.vue'
import VersionTimeline from './VersionTimeline.vue'

const props = defineProps<{
  open: boolean
  itemId?: string
  claims: ClaimView[]
  evidence: EvidenceView[]
}>()
const emit = defineEmits<{ close: [] }>()
const page = ref<DocumentPageView | null>(null)
const timeline = ref<VersionTimelineResponse | null>(null)
const diff = ref<VersionDiffResponse | null>(null)
const loading = ref(false)
const loadError = ref(false)

const model = computed({
  get: () => props.open,
  set: (value: boolean) => { if (!value) emit('close') },
})

const firstPdfLocator = computed(() => {
  for (const entry of props.evidence) {
    if (entry.locator && entry.locator.type !== 'HTML_PARAGRAPH') return entry.locator
  }
  return null
})

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    await loadRound03Evidence()
  },
)

async function loadPage(versionId: string, pageNumber: number): Promise<void> {
  page.value = await $fetch<DocumentPageView>(
    `/api/v1/document-versions/${versionId}/pages/${pageNumber}`,
  )
}

async function loadRound03Evidence(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const locator = firstPdfLocator.value
    const firstEvidence = props.evidence.find((entry) => entry.locator === locator)
    if (locator && firstEvidence?.document_version_id) {
      await loadPage(firstEvidence.document_version_id, locator.page_number)
    }
    if (props.itemId) {
      timeline.value = await $fetch<VersionTimelineResponse>(
        `/api/v1/items/${props.itemId}/versions`,
      )
      const versions = timeline.value.versions
      if (versions.length >= 2) {
        const from = versions.at(-2)
        const to = versions.at(-1)
        if (from && to) {
          diff.value = await $fetch<VersionDiffResponse>(
            `/api/v1/items/${props.itemId}/diff`,
            { query: { from: from.version_id, to: to.version_id } },
          )
        }
      }
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function changePage(pageNumber: number): Promise<void> {
  if (page.value) await loadPage(page.value.document_version_id, pageNumber)
}
</script>

<template>
  <ResponsiveDrawer
    v-model="model"
    title="原文段落与页码定位"
    description="浏览器仅加载服务端生成的有界 PNG，不加载或执行原始 PDF。"
    close-label="关闭证据抽屉"
  >
    <div class="evidence-drawer">
      <p v-if="loading" role="status">正在加载页码和版本证据…</p>
      <p v-if="loadError" class="evidence-drawer__warning" role="alert">
        页码预览或版本差异暂不可用；字段证据仍保留在下方。
      </p>

      <PdfEvidenceViewer
        v-if="page"
        :page="page"
        :evidence="evidence"
        @page="changePage"
      />
      <VersionTimeline v-if="timeline" :timeline="timeline" />
      <DiffView v-if="diff" :diff="diff" />

      <section aria-labelledby="evidence-list-title">
        <h3 id="evidence-list-title">字段证据</h3>
        <p class="evidence-drawer__notice">
          证据摘录仅用于核对字段；完整上下文请查看官方原文。
        </p>
        <ol class="evidence-drawer__list">
          <li v-for="entry in evidence" :key="entry.id">
            <span v-if="entry.locator && entry.locator.type !== 'HTML_PARAGRAPH'">
              第 {{ entry.locator.page_number }} 页 · {{ entry.locator.type }}
              <template v-if="entry.locator.type === 'PDF_OCR'">
                · OCR 置信度 {{ (entry.locator.confidence_bps / 100).toFixed(1) }}%
              </template>
            </span>
            <span v-else>{{ entry.paragraph_id }} · 字符 {{ entry.char_start }}–{{ entry.char_end }}</span>
            <blockquote>{{ entry.excerpt }}</blockquote>
            <p>
              支持字段：{{ claims.filter((claim) => entry.claim_ids.includes(claim.id)).map((claim) => claim.label).join('、') }}
            </p>
            <a :href="entry.original_url" target="_blank" rel="noreferrer">在官方原文中查看</a>
          </li>
        </ol>
      </section>
    </div>
  </ResponsiveDrawer>
</template>

<style scoped>
.evidence-drawer { display: grid; gap: var(--spacing-6); }
.evidence-drawer h3 { margin: 0; }
.evidence-drawer__warning, .evidence-drawer__notice { padding: var(--spacing-3); color: var(--color-ink-700); border-radius: var(--radius-sm); }
.evidence-drawer__warning { background: var(--color-reviewPending-50); }
.evidence-drawer__notice { background: var(--color-brand-50); }
.evidence-drawer__list { display: grid; padding: 0; list-style: none; gap: var(--spacing-4); }
.evidence-drawer__list li { padding: var(--spacing-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.evidence-drawer__list span, .evidence-drawer__list p { color: var(--color-ink-500); font-size: var(--text-sm); }
.evidence-drawer__list blockquote { margin: var(--spacing-3) 0; padding-left: var(--spacing-3); color: var(--color-ink-900); border-left: 3px solid var(--color-brand-400); }
.evidence-drawer__list a { color: var(--color-brand-700); }
</style>
