<script setup lang="ts">
import type {
  ClaimConflict,
  ClaimConflictDecisionRequest,
  ClaimConflictDecisionResponse,
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

const busyConflictId = ref<string | null>(null)
const decisionError = ref<string | null>(null)
const decisionSuccess = ref<string | null>(null)

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
