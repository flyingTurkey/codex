<script setup lang="ts">
import type { OwnerExceptionView } from '@srbg/contracts'
import { EmptyState, PageHeader, Skeleton, StatusBadge } from '@srbg/ui'

import { createUuidV7 } from '../utils/uuid-v7'

const statusFilter = ref<'OPEN' | 'RESOLVED'>('OPEN')
const query = computed(() => ({ kind: 'TECHNICAL', status: statusFilter.value, limit: 50 }))
const { data: exceptions, error, status, refresh } = await useFetch<OwnerExceptionView[]>(
  '/api/v2/owner/exceptions',
  { server: false, query, default: () => [], retry: 0, timeout: 5_000 },
)
const retryingIds = ref<string[]>([])
const disablingSourceIds = ref<string[]>([])
const actionMessage = ref<string | null>(null)
const actionError = ref<string | null>(null)

const reasonLabels: Readonly<Record<string, string>> = {
  TECHNICAL_RETRYABLE: '可重试技术故障',
  TECHNICAL_EXHAUSTED: '自动重试已耗尽',
  AI_SCHEMA_INVALID: 'AI 输出格式无效',
  NETWORK_TIMEOUT: '网络请求超时',
  PROVIDER_TIMEOUT: '模型服务超时',
  TRANSIENT_UNAVAILABLE: '临时服务不可用',
  DATABASE_TEMPORARILY_UNAVAILABLE: '数据库临时不可用',
  OBJECT_STORE_TEMPORARILY_UNAVAILABLE: '对象存储临时不可用',
  QUEUE_CONTENTION: '任务队列拥堵',
  UNSUPPORTED_DOCUMENT_MIME: '不支持的文档格式',
  DOCUMENT_VALIDATION_FAILED: '文档验证失败',
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai',
  }).format(new Date(value))
}

async function retryNow(item: OwnerExceptionView): Promise<void> {
  if (retryingIds.value.includes(item.id)) return
  retryingIds.value = [...retryingIds.value, item.id]
  actionMessage.value = null
  actionError.value = null
  try {
    await $fetch(`/api/v2/owner/exceptions/${item.id}/commands`, {
      method: 'POST',
      headers: {
        'If-Match': `"${item.version}"`,
        'Idempotency-Key': createUuidV7(),
      },
      body: {
        exception_id: item.id,
        event_type: 'RETRY_REQUESTED',
        expected_version: item.version,
      },
      retry: 0,
      timeout: 5_000,
    })
    actionMessage.value = '已记录立即重试请求，后台将从耐久状态恢复。'
    await refresh()
  }
  catch {
    actionError.value = '立即重试请求失败，请刷新后重试。'
  }
  finally {
    retryingIds.value = retryingIds.value.filter(id => id !== item.id)
  }
}

async function disableSource(item: OwnerExceptionView): Promise<void> {
  if (!item.source_id || disablingSourceIds.value.includes(item.source_id)) return
  disablingSourceIds.value = [...disablingSourceIds.value, item.source_id]
  actionMessage.value = null
  actionError.value = null
  try {
    await $fetch(`/api/v1/sources/${item.source_id}`, {
      method: 'PATCH',
      body: { desired_enabled: false },
      retry: 0,
      timeout: 5_000,
    })
    actionMessage.value = '已记录停用来源的个人意图；实际运行状态仍由服务端门禁决定。'
  }
  catch {
    actionError.value = '来源停用失败，服务端原状态未被页面覆盖。'
  }
  finally {
    disablingSourceIds.value = disablingSourceIds.value.filter(id => id !== item.source_id)
  }
}
</script>

<template>
  <section class="technical-page">
    <PageHeader
      title="技术异常"
      eyebrow="Owner 运行控制"
      description="查看已耗尽的自动重试，可立即重试或停用对应来源。恢复成功后异常会自动关闭。"
    />
    <div class="technical-page__toolbar">
      <label for="technical-status">状态</label>
      <select id="technical-status" v-model="statusFilter">
        <option value="OPEN">待处理</option>
        <option value="RESOLVED">已恢复</option>
      </select>
      <button type="button" @click="() => refresh()">刷新</button>
    </div>
    <p v-if="actionMessage" role="status" class="technical-page__message">{{ actionMessage }}</p>
    <p v-if="actionError" role="alert" class="technical-page__error">{{ actionError }}</p>
    <Skeleton v-if="status === 'idle' || status === 'pending'" :lines="5" label="正在加载技术异常" />
    <p v-else-if="error" role="alert">技术异常加载失败，请稍后刷新。</p>
    <ol v-else-if="exceptions?.length" class="technical-page__list">
      <li v-for="item in exceptions" :key="item.id">
        <header>
          <StatusBadge
            :tone="item.status === 'OPEN' ? 'conflict' : 'verified'"
            :label="item.status === 'OPEN' ? '待处理' : '已恢复'"
          />
          <strong>{{ reasonLabels[item.technical_reason_code ?? ''] ?? item.technical_reason_code ?? item.reason_codes.map(code => reasonLabels[code] ?? code).join('、') }}</strong>
        </header>
        <dl>
          <div><dt>尝试次数</dt><dd>{{ item.attempt_count }}</dd></div>
          <div v-if="item.technical_reason_code"><dt>原因代码</dt><dd class="technical-page__mono">{{ item.technical_reason_code }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ formatTime(item.updated_at) }}</dd></div>
          <div v-if="item.source_id"><dt>来源标识</dt><dd class="technical-page__mono">{{ item.source_id }}</dd></div>
        </dl>
        <div v-if="item.status === 'OPEN'" class="technical-page__actions">
          <button type="button" :disabled="retryingIds.includes(item.id)" @click="retryNow(item)">
            {{ retryingIds.includes(item.id) ? '正在提交…' : '立即重试' }}
          </button>
          <button
            v-if="item.source_id"
            type="button"
            class="technical-page__secondary"
            :disabled="disablingSourceIds.includes(item.source_id)"
            @click="disableSource(item)"
          >
            {{ disablingSourceIds.includes(item.source_id) ? '正在停用…' : '停用来源' }}
          </button>
        </div>
      </li>
    </ol>
    <EmptyState v-else title="没有技术异常" description="当前筛选范围内没有需要处理的技术故障。" />
  </section>
</template>

<style scoped>
.technical-page { display:grid; width:min(100%,var(--srbg-layout-content-max)); margin-inline:auto; gap:var(--spacing-5); }
.technical-page__toolbar,.technical-page__actions,header { display:flex; align-items:center; flex-wrap:wrap; gap:var(--spacing-2); }
.technical-page__toolbar select,.technical-page button { min-height:2.75rem; }
.technical-page__list { display:grid; padding:0; list-style:none; gap:var(--spacing-3); }
.technical-page__list li { display:grid; padding:var(--spacing-4); background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); gap:var(--spacing-3); }
.technical-page dl { display:flex; flex-wrap:wrap; gap:var(--spacing-4); margin:0; color:var(--color-ink-600); }
.technical-page dl div { display:flex; gap:var(--spacing-1); }
.technical-page dd { margin:0; }
.technical-page__mono { font-family:var(--font-mono); overflow-wrap:anywhere; }
.technical-page__secondary { background:var(--color-surface-muted); color:var(--color-ink-900); border:1px solid var(--color-border-strong); }
.technical-page__message { color:var(--color-verified-700); }
.technical-page__error { color:var(--color-conflict-700); }
@media (max-width: 48rem) { .technical-page dl { display:grid; gap:var(--spacing-2); } }
</style>
