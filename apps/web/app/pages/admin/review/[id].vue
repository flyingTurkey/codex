<script setup lang="ts">
import type { ReviewDecisionResponse, ReviewTaskDetail } from '@srbg/contracts'
import { PageHeader, StatusBadge } from '@srbg/ui'
import { ref } from 'vue'

import EvidenceDrawer from '../../../components/EvidenceDrawer.vue'
import IntelligenceCard from '../../../components/IntelligenceCard.vue'

const route = useRoute()
const taskId = String(route.params.id)
const { data: detail, status, error, refresh } = await useFetch<ReviewTaskDetail>(
  `/api/v1/admin/review-tasks/${taskId}`,
  { server: false, retry: 0, timeout: 5_000 },
)
const reason = ref('字段与官方原文证据一致')
const submitting = ref(false)
const decisionError = ref<string | null>(null)
const evidenceOpen = ref(false)

async function decide(action: 'APPROVE' | 'REJECT'): Promise<void> {
  submitting.value = true
  decisionError.value = null
  try {
    await $fetch<ReviewDecisionResponse>(
      `/api/v1/admin/review-tasks/${taskId}/decisions`,
      { method: 'POST', body: { action, reason: reason.value } },
    )
    await refresh()
  } catch {
    decisionError.value = '审核决定未能提交，请检查职责分离与发布门禁。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="review-detail">
    <PageHeader
      title="R3 审核详情"
      eyebrow="字段证据与发布门禁"
      description="候选内容自报的来源等级、评分或审核状态不作为授权依据。"
    />
    <p v-if="status === 'pending'" role="status">正在加载审核证据…</p>
    <p v-else-if="error" role="alert">审核详情暂时不可用。</p>
    <template v-else-if="detail">
      <StatusBadge
        :label="detail.task.status === 'PENDING' ? '待审核' : detail.task.status === 'APPROVED' ? '已批准' : '已拒绝'"
        :tone="detail.task.status === 'PENDING' ? 'pending' : detail.task.status === 'APPROVED' ? 'verified' : 'conflict'"
      />
      <IntelligenceCard :item="detail.item" />

      <section class="review-detail__claims">
        <h2>规则解析字段</h2>
        <dl>
          <div v-for="claim in detail.claims" :key="claim.id">
            <dt>{{ claim.label }}</dt>
            <dd>{{ claim.value }}</dd>
          </div>
        </dl>
        <button type="button" @click="evidenceOpen = true">
          打开 {{ detail.evidence.length }} 条段落证据
        </button>
      </section>

      <form v-if="detail.task.status === 'PENDING'" class="review-detail__decision" @submit.prevent>
        <label>
          审核说明
          <textarea v-model="reason" required minlength="1" maxlength="1000" />
        </label>
        <p v-if="decisionError" role="alert">{{ decisionError }}</p>
        <div>
          <button type="button" :disabled="submitting" @click="decide('REJECT')">拒绝</button>
          <button type="button" :disabled="submitting" @click="decide('APPROVE')">
            批准并发布
          </button>
        </div>
      </form>
    </template>

    <EvidenceDrawer
      :open="evidenceOpen"
      :item-id="detail?.item.id"
      :claims="detail?.claims ?? []"
      :evidence="detail?.evidence ?? []"
      @close="evidenceOpen = false"
    />
  </section>
</template>

<style scoped>
.review-detail {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.review-detail__claims,
.review-detail__decision {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.review-detail__claims h2 {
  margin-top: 0;
}

.review-detail__claims dl {
  display: grid;
  gap: var(--spacing-3);
}

.review-detail__claims dt,
.review-detail__decision label {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

.review-detail__claims dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-900);
}

.review-detail__decision label {
  display: grid;
  gap: var(--spacing-2);
}

.review-detail__decision textarea {
  min-height: 6rem;
  padding: var(--spacing-3);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail__decision div {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  margin-top: var(--spacing-3);
}

.review-detail button {
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-brand-700);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail button:last-child {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}
</style>
