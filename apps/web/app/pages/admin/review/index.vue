<script setup lang="ts">
import type {
  ClaimConflict,
  ClaimConflictDecisionRequest,
  ClaimConflictDecisionResponse,
  ProductNormalizationCandidateView,
  ProductNormalizationDecisionRequest,
  ReviewTaskSummary,
} from '@srbg/contracts'
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import ClaimConflictPanel from '../../../components/ClaimConflictPanel.vue'

const { data: tasks, status: taskStatus, error: taskError } = await useFetch<ReviewTaskSummary[]>(
  '/api/v1/admin/review-tasks',
  { server: false, retry: 0, timeout: 5_000 },
)
const {
  data: conflicts,
  status: conflictStatus,
  error: conflictError,
  refresh: refreshConflicts,
} = await useFetch<ClaimConflict[]>('/api/v1/admin/claim-conflicts', {
  server: false,
  retry: 0,
  timeout: 5_000,
})
const {
  data: productCandidates,
  status: productCandidateStatus,
  error: productCandidateError,
  refresh: refreshProductCandidates,
} = await useFetch<ProductNormalizationCandidateView[]>(
  '/api/v1/admin/product-normalization-candidates',
  { server: false, retry: 0, timeout: 5_000 },
)

const busyConflictId = ref<string | null>(null)
const decisionError = ref<string | null>(null)
const decisionSuccess = ref<string | null>(null)
const productDecision = ref<Record<string, ProductNormalizationDecisionRequest['action']>>({})
const productReason = ref<Record<string, string>>({})
const busyProductCandidateId = ref<string | null>(null)
const productDecisionMessage = ref<string | null>(null)

const conflictErrorMessage = computed(() => {
  if (decisionError.value) return decisionError.value
  if (!conflictError.value) return null
  if (conflictError.value.statusCode === 403) return '冲突队列仅对 reviewer 角色开放。'
  return '关键字段冲突暂时无法加载。'
})

async function decideConflict(
  conflictId: string,
  decision: ClaimConflictDecisionRequest,
): Promise<void> {
  if (!decision.reason.trim()) return
  busyConflictId.value = conflictId
  decisionError.value = null
  decisionSuccess.value = null
  try {
    await $fetch<ClaimConflictDecisionResponse>(
      `/api/v1/admin/claim-conflicts/${conflictId}/decisions`,
      {
        method: 'POST',
        body: decision,
        retry: 0,
        timeout: 5_000,
      },
    )
    await refreshConflicts()
    decisionSuccess.value = '冲突决定已记录，列表已刷新。'
  } catch {
    decisionError.value = '冲突决定未能保存；事实未发生变更，请重试。'
  } finally {
    busyConflictId.value = null
  }
}

async function decideProductCandidate(candidateId: string): Promise<void> {
  const action = productDecision.value[candidateId] ?? 'KEEP_DISTINCT'
  const reason = productReason.value[candidateId]?.trim()
  if (!reason) {
    productDecisionMessage.value = '请填写归一决定依据。'
    return
  }
  busyProductCandidateId.value = candidateId
  productDecisionMessage.value = null
  try {
    await $fetch(`/api/v1/admin/product-normalization-candidates/${candidateId}/decision`, {
      method: 'POST',
      body: { action, reason } satisfies ProductNormalizationDecisionRequest,
      retry: 0,
      timeout: 5_000,
    })
    await refreshProductCandidates()
    productDecisionMessage.value = '型号与版本归一决定已记录。'
  } catch {
    productDecisionMessage.value = '归一决定保存失败，候选状态未改变。'
  } finally {
    busyProductCandidateId.value = null
  }
}
</script>

<template>
  <section class="review-queue">
    <PageHeader
      title="审核工作台"
      eyebrow="R3 人工复核"
      description="审核人与提交人必须分离；批准动作只能通过统一发布服务。"
    />
    <ClaimConflictPanel
      :conflicts="conflicts ?? []"
      :loading="conflictStatus === 'idle' || conflictStatus === 'pending'"
      :busy-conflict-id="busyConflictId"
      :error-message="conflictErrorMessage"
      :success-message="decisionSuccess"
      @decide="decideConflict"
    />

    <section class="review-queue__product-candidates" aria-labelledby="product-candidate-title">
      <h2 id="product-candidate-title">型号与版本归一候选</h2>
      <p>同名不同型号默认保持独立；合并别名或链接新版本必须由审核人明确决定。</p>
      <p v-if="productCandidateStatus === 'pending'" role="status">正在加载归一候选…</p>
      <p v-else-if="productCandidateError" role="alert">归一候选暂时不可用。</p>
      <p v-if="productDecisionMessage" aria-live="polite">{{ productDecisionMessage }}</p>
      <ol v-if="productCandidates?.length" class="review-queue__list">
        <li v-for="candidate in productCandidates" :key="candidate.id">
          <div>
            <StatusBadge tone="pending" label="待人工归一" />
            <h3>{{ candidate.incoming_label }}</h3>
            <p>候选：{{ candidate.candidate_label }} · {{ candidate.candidate_type }}</p>
            <label>
              决定
              <select v-model="productDecision[candidate.id]">
                <option value="KEEP_DISTINCT">保持不同型号/版本</option>
                <option value="LINK_AS_NEW_VERSION">链接为新版本</option>
                <option value="MERGE_ALIAS">合并为别名</option>
              </select>
            </label>
            <label>
              决定依据
              <textarea v-model="productReason[candidate.id]" required maxlength="1000" />
            </label>
          </div>
          <button
            type="button"
            :disabled="busyProductCandidateId === candidate.id"
            @click="decideProductCandidate(candidate.id)"
          >
            提交归一决定
          </button>
        </li>
      </ol>
      <EmptyState v-else-if="!productCandidateError" title="暂无归一候选" icon="List" />
    </section>

    <section class="review-queue__tasks" aria-labelledby="review-task-title">
      <h2 id="review-task-title">R3 审核任务</h2>
      <p v-if="taskStatus === 'pending'" role="status">正在加载审核任务…</p>
      <p v-else-if="taskError" role="alert">审核队列暂时不可用。</p>
      <ol v-else-if="tasks?.length" class="review-queue__list">
        <li v-for="task in tasks" :key="task.id">
          <div>
            <StatusBadge
              :label="task.status === 'PENDING' ? '待审核' : task.status === 'APPROVED' ? '已批准' : '已拒绝'"
              :tone="task.status === 'PENDING' ? 'pending' : task.status === 'APPROVED' ? 'verified' : 'conflict'"
            />
            <h3><a :href="`/admin/review/${task.id}`">{{ task.title }}</a></h3>
            <p>{{ task.source_name }} · {{ task.risk_level }}</p>
          </div>
          <a :href="`/admin/review/${task.id}`">查看字段证据</a>
        </li>
      </ol>
      <EmptyState
        v-else
        title="暂无审核任务"
        description="新发现的 R3 安全规定或安全案例会进入这里。"
        icon="ShieldCheck"
      />
    </section>
  </section>
</template>

<style scoped>
.review-queue {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.review-queue__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-3);
}

.review-queue__tasks {
  display: grid;
  gap: var(--spacing-4);
}

.review-queue__product-candidates {
  display: grid;
  gap: var(--spacing-4);
}

.review-queue__product-candidates label {
  display: grid;
  margin-top: var(--spacing-2);
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}

.review-queue__product-candidates select,
.review-queue__product-candidates textarea,
.review-queue__product-candidates button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-queue__tasks > h2 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
}

.review-queue__list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.review-queue__list h3 {
  margin: var(--spacing-2) 0;
  font-size: var(--text-lg);
}

.review-queue__list p {
  margin: 0;
  color: var(--color-ink-500);
}

.review-queue__list a {
  color: var(--color-brand-700);
}
</style>
