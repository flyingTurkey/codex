<script setup lang="ts">
import type { FeedSuppressionRuleView } from '@srbg/contracts'
import { EmptyState, PageHeader, Skeleton, StatusBadge } from '@srbg/ui'

import { createUuidV7 } from '../utils/uuid-v7'

const { data: rules, error, status, refresh } = await useFetch<FeedSuppressionRuleView[]>(
  '/api/v2/owner/suppressions',
  { server: false, query: { active_only: true }, default: () => [], retry: 0, timeout: 5_000 },
)
const revokingIds = ref<string[]>([])
type SuppressionScope = 'EVENT' | 'PRIMARY_TYPE' | 'ENGINEERING_OBJECT' | 'SPECIALTY_FACET' | 'EQUIPMENT_DOMAIN' | 'SOURCE' | 'CUSTOM_TOPIC'
const newScope = ref<SuppressionScope>('CUSTOM_TOPIC')
const newTarget = ref('')
const newReason = ref<'OWNER_PREFERENCE' | 'CLASSIFICATION_ERROR'>('OWNER_PREFERENCE')
const creating = ref(false)
const message = ref<string | null>(null)
const problem = ref<string | null>(null)

const scopeLabels: Readonly<Record<string, string>> = {
  EVENT: '单条 Event',
  PRIMARY_TYPE: '主类型',
  ENGINEERING_OBJECT: '工程对象',
  SPECIALTY_FACET: '专业方向',
  EQUIPMENT_DOMAIN: '设备领域',
  SOURCE: '来源',
  CUSTOM_TOPIC: '自定义主题',
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai',
  }).format(new Date(value))
}

async function revoke(item: FeedSuppressionRuleView): Promise<void> {
  if (revokingIds.value.includes(item.id)) return
  revokingIds.value = [...revokingIds.value, item.id]
  message.value = null
  problem.value = null
  try {
    await $fetch('/api/v2/owner/suppressions', {
      method: 'POST',
      headers: {
        'If-Match': `"${item.id}"`,
        'Idempotency-Key': createUuidV7(),
      },
      body: {
        action: 'REVOKE',
        scope: item.scope,
        target_key: item.target_key,
        feedback_reason: item.feedback_reason,
        supersedes_rule_id: item.id,
      },
      retry: 0,
      timeout: 5_000,
    })
    message.value = '已撤销隐藏偏好；当前仍满足 PublicationService 门禁的内容会自动恢复。'
    await refresh()
  }
  catch {
    problem.value = '撤销失败，原有隐藏偏好保持不变，请刷新后重试。'
  }
  finally {
    revokingIds.value = revokingIds.value.filter(id => id !== item.id)
  }
}

async function createRule(): Promise<void> {
  if (!newTarget.value.trim() || creating.value) return
  creating.value = true
  message.value = null
  problem.value = null
  try {
    await $fetch('/api/v2/owner/suppressions', {
      method: 'POST',
      headers: { 'Idempotency-Key': createUuidV7() },
      body: {
        action: 'ACTIVATE',
        scope: newScope.value,
        target_key: newTarget.value.trim(),
        feedback_reason: newReason.value,
      },
      retry: 0,
      timeout: 5_000,
    })
    newTarget.value = ''
    message.value = '新的 Feed 隐藏偏好已生效。'
    await refresh()
  }
  catch {
    problem.value = '创建失败；请检查匹配键是否符合所选范围。'
  }
  finally {
    creating.value = false
  }
}
</script>

<template>
  <section class="suppression-page">
    <PageHeader
      title="Feed 偏好"
      eyebrow="Owner 展示控制"
      description="管理只影响读取展示的隐藏规则；原文、证据、claims、decision 与历史投影始终保留。"
    />
    <form class="suppression-page__create" @submit.prevent="createRule">
      <h2>新增隐藏规则</h2>
      <label for="suppression-scope">范围</label>
      <select id="suppression-scope" v-model="newScope">
        <option v-for="(label, value) in scopeLabels" :key="value" :value="value">{{ label }}</option>
      </select>
      <label for="suppression-target">精确匹配键</label>
      <input id="suppression-target" v-model="newTarget" required maxlength="300" autocomplete="off">
      <label for="suppression-reason">原因</label>
      <select id="suppression-reason" v-model="newReason">
        <option value="OWNER_PREFERENCE">个人偏好</option>
        <option value="CLASSIFICATION_ERROR">分类反馈</option>
      </select>
      <button type="submit" :disabled="creating || !newTarget.trim()">
        {{ creating ? '正在创建…' : '创建隐藏规则' }}
      </button>
    </form>
    <p v-if="message" role="status" class="suppression-page__message">{{ message }}</p>
    <p v-if="problem" role="alert" class="suppression-page__error">{{ problem }}</p>
    <Skeleton v-if="status === 'idle' || status === 'pending'" :lines="4" label="正在加载 Feed 偏好" />
    <p v-else-if="error" role="alert">Feed 偏好加载失败，请稍后刷新。</p>
    <ol v-else-if="rules?.length" class="suppression-page__list">
      <li v-for="item in rules" :key="item.id">
        <header>
          <StatusBadge tone="pending" label="正在隐藏" />
          <strong>{{ scopeLabels[item.scope] ?? item.scope }}</strong>
        </header>
        <dl>
          <div><dt>匹配键</dt><dd>{{ item.target_key }}</dd></div>
          <div><dt>生效时间</dt><dd>{{ formatTime(item.effective_at) }}</dd></div>
        </dl>
        <button type="button" :disabled="revokingIds.includes(item.id)" @click="revoke(item)">
          {{ revokingIds.includes(item.id) ? '正在撤销…' : '撤销隐藏' }}
        </button>
      </li>
    </ol>
    <EmptyState v-else title="没有生效中的隐藏规则" description="从 Feed 情报卡隐藏内容后，可在这里统一撤销。" />
  </section>
</template>

<style scoped>
.suppression-page { display:grid; width:min(100%,var(--srbg-layout-content-max)); margin-inline:auto; gap:var(--spacing-5); }
.suppression-page__list { display:grid; padding:0; list-style:none; gap:var(--spacing-3); }
.suppression-page__create { display:grid; grid-template-columns:8rem minmax(0,1fr); padding:var(--spacing-4); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); gap:var(--spacing-3); }
.suppression-page__create h2 { grid-column:1/-1; margin:0; }
.suppression-page__create input,.suppression-page__create select { min-height:2.75rem; }
.suppression-page__create button { grid-column:2; }
.suppression-page__list li { display:grid; padding:var(--spacing-4); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); gap:var(--spacing-3); }
.suppression-page header { display:flex; align-items:center; flex-wrap:wrap; gap:var(--spacing-2); }
.suppression-page dl { display:grid; margin:0; gap:var(--spacing-2); }
.suppression-page dl div { display:grid; grid-template-columns:7rem minmax(0,1fr); gap:var(--spacing-2); }
.suppression-page dd { margin:0; overflow-wrap:anywhere; }
.suppression-page button { justify-self:start; min-height:2.75rem; }
.suppression-page__message { color:var(--color-verified-700); }
.suppression-page__error { color:var(--color-conflict-700); }
@media (max-width:40rem) { .suppression-page dl div,.suppression-page__create { grid-template-columns:1fr; } .suppression-page__create h2,.suppression-page__create button { grid-column:1; } }
</style>
