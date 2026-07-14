<script setup lang="ts">
import type { ReviewTaskSummary } from '@srbg/contracts'
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'

const { data: tasks, status, error } = await useFetch<ReviewTaskSummary[]>(
  '/api/v1/admin/review-tasks',
  { server: false, retry: 0, timeout: 5_000 },
)
</script>

<template>
  <section class="review-queue">
    <PageHeader
      title="审核工作台"
      eyebrow="R3 人工复核"
      description="审核人与提交人必须分离；批准动作只能通过统一发布服务。"
    />
    <p v-if="status === 'pending'" role="status">正在加载审核任务…</p>
    <p v-else-if="error" role="alert">审核队列暂时不可用。</p>
    <ol v-else-if="tasks?.length" class="review-queue__list">
      <li v-for="task in tasks" :key="task.id">
        <div>
          <StatusBadge
            :label="task.status === 'PENDING' ? '待审核' : task.status === 'APPROVED' ? '已批准' : '已拒绝'"
            :tone="task.status === 'PENDING' ? 'pending' : task.status === 'APPROVED' ? 'verified' : 'conflict'"
          />
          <h2><a :href="`/admin/review/${task.id}`">{{ task.title }}</a></h2>
          <p>{{ task.source_name }} · {{ task.risk_level }}</p>
        </div>
        <a :href="`/admin/review/${task.id}`">查看字段证据</a>
      </li>
    </ol>
    <EmptyState
      v-else
      title="暂无审核任务"
      description="新发现的 R3 安全规定会进入这里。"
      icon="ShieldCheck"
    />
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

.review-queue__list h2 {
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
