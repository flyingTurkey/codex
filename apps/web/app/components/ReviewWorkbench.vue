<script setup lang="ts">
import type {
  ConfirmedFact,
  DocumentPageView,
  ReviewTaskDetail,
  UnverifiedFact,
} from '@srbg/contracts'
import { StatusBadge } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import FactList from './FactList.vue'
import IntelligenceCard from './IntelligenceCard.vue'
import PdfEvidenceViewer from './PdfEvidenceViewer.vue'

const props = defineProps<{ detail: ReviewTaskDetail }>()
const emit = defineEmits<{ evidence: [claimId?: string] }>()
const page = ref<DocumentPageView | null>(null)
const pageError = ref(false)

const acceptedFacts = computed<ConfirmedFact[]>(() => props.detail.claims
  .filter((claim) => claim.decision_status === 'ACCEPTED')
  .map((claim) => ({
    source_item_id: props.detail.item.id,
    claim_id: claim.id,
    field: claim.claim_type as ConfirmedFact['field'],
    label: claim.label,
    value: claim.value,
    unit: null,
    evidence_ids: claim.evidence_ids,
    reviewed_at: new Date().toISOString(),
  })))

const pendingFacts = computed<UnverifiedFact[]>(() => props.detail.claims
  .filter((claim) => claim.decision_status !== 'ACCEPTED')
  .map((claim) => ({
    source_item_id: props.detail.item.id,
    claim_id: claim.id,
    conflict_id: null,
    field: claim.claim_type as UnverifiedFact['field'],
    label: claim.label,
    value: null,
    display_value: '待核实',
    evidence_ids: claim.evidence_ids,
    status: claim.decision_status === 'REJECTED' ? 'CONFLICTING' : 'PENDING_REVIEW',
    reason: claim.decision_status === 'REJECTED' ? '候选字段已拒绝' : '等待人工逐字段决定',
  })))

const pdfEvidence = computed(() => props.detail.evidence.filter((entry) =>
  entry.document_version_id && entry.locator?.type !== 'HTML_PARAGRAPH'))

async function loadPage(pageNumber?: number): Promise<void> {
  const evidence = pdfEvidence.value[0]
  if (!evidence?.document_version_id) return
  const locatorPage = evidence.locator && evidence.locator.type !== 'HTML_PARAGRAPH'
    ? evidence.locator.page_number
    : 1
  try {
    page.value = await $fetch<DocumentPageView>(
      `/api/v1/document-versions/${evidence.document_version_id}/pages/${pageNumber ?? locatorPage}`,
      { retry: 0, timeout: 5_000 },
    )
    pageError.value = false
  } catch {
    pageError.value = true
  }
}

watch(pdfEvidence, () => void loadPage(), { immediate: true })
</script>

<template>
  <section class="review-workbench" aria-label="三栏审核工作台">
    <section class="review-workbench__source" aria-labelledby="workbench-source">
      <header>
        <h2 id="workbench-source">原文与定位证据</h2>
        <StatusBadge tone="info" label="不可信原文输入" />
      </header>
      <PdfEvidenceViewer
        v-if="page"
        :page="page"
        :evidence="detail.evidence"
        @page="loadPage"
      />
      <p v-else-if="pageError" role="status">PDF 安全预览暂不可用，可继续核对段落证据。</p>
      <div v-else class="review-workbench__excerpts">
        <blockquote v-for="entry in detail.evidence" :key="entry.id">
          {{ entry.excerpt }}
        </blockquote>
      </div>
      <button type="button" @click="emit('evidence')">打开全部证据</button>
    </section>

    <section class="review-workbench__facts" aria-labelledby="workbench-facts">
      <h2 id="workbench-facts">字段与证据</h2>
      <FactList
        title="已接受字段"
        :facts="acceptedFacts"
        variant="confirmed"
        empty-description="只有 accepted claims 才能进入审核后摘要。"
        @evidence="emit('evidence')"
      />
      <FactList
        title="待核实或已拒绝字段"
        :facts="pendingFacts"
        variant="unverified"
        @evidence="emit('evidence')"
      />
    </section>

    <aside class="review-workbench__decision" aria-labelledby="workbench-decision">
      <header>
        <h2 id="workbench-decision">摘要对照与决定</h2>
        <StatusBadge
          :tone="detail.item.ai_assistance?.status === 'ASSISTED' ? 'info' : 'pending'"
          :label="detail.item.ai_assistance?.status === 'ASSISTED' ? 'AI 辅助' : '无 AI 题录降级'"
        />
      </header>
      <IntelligenceCard :item="detail.item" />
      <details v-if="detail.item.ai_assistance">
        <summary>Prompt / Schema / 模型版本</summary>
        <dl>
          <div><dt>Prompt</dt><dd>{{ detail.item.ai_assistance.prompt_version ?? '未运行' }}</dd></div>
          <div><dt>Schema</dt><dd>{{ detail.item.ai_assistance.schema_version ?? '未运行' }}</dd></div>
          <div><dt>模型</dt><dd>{{ detail.item.ai_assistance.model_profile ?? '未运行' }}</dd></div>
        </dl>
      </details>
      <p class="review-workbench__boundary">
        模型建议不具授权性；R3/R4、安全原因、责任和法规效力必须人工决定并填写理由。
      </p>
      <slot name="actions" />
    </aside>
  </section>
</template>

<style scoped>
.review-workbench {
  display: grid;
  grid-template-columns: minmax(18rem, 1fr) minmax(20rem, 1.05fr) minmax(19rem, 0.9fr);
  align-items: start;
  gap: var(--spacing-4);
}
.review-workbench > section,
.review-workbench > aside {
  display: grid;
  min-width: 0;
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-4);
}
.review-workbench header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--spacing-2); }
.review-workbench h2 { margin: 0; color: var(--color-ink-900); font-size: var(--text-lg); }
.review-workbench__excerpts { display: grid; max-height: 34rem; overflow: auto; gap: var(--spacing-3); }
.review-workbench blockquote { margin: 0; padding: var(--spacing-3); background: var(--color-surfaceMuted); border-left: var(--spacing-1) solid var(--color-brand-400); }
.review-workbench button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-brand-700); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.review-workbench details dl { display: grid; margin: var(--spacing-3) 0 0; gap: var(--spacing-2); }
.review-workbench details div { display: grid; grid-template-columns: 5rem 1fr; }
.review-workbench details dd { margin: 0; overflow-wrap: anywhere; }
.review-workbench__boundary { margin: 0; padding: var(--spacing-3); color: var(--color-ink-700); background: var(--color-reviewPending-50); border-radius: var(--radius-sm); }
@media (max-width: 79.999rem) { .review-workbench { grid-template-columns: repeat(2, minmax(0, 1fr)); } .review-workbench__decision { grid-column: 1 / -1; } }
@media (max-width: 47.999rem) { .review-workbench { grid-template-columns: 1fr; } .review-workbench__decision { grid-column: auto; } }
</style>
