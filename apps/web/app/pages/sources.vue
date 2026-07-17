<script setup lang="ts">
import type { PersonalSourceView } from '@srbg/contracts'

const { data: sources, error, status, refresh } = await useFetch<PersonalSourceView[]>(
  '/api/v1/sources',
  {
    server: false,
    default: () => [],
    retry: 0,
    timeout: 5_000,
  },
)
const busySourceIds = ref<string[]>([])
const actionError = ref<string | null>(null)
const actionMessage = ref<string | null>(null)

const runtimeLabels: Readonly<Record<PersonalSourceView['runtime_state'], string>> = {
  PENDING_CONFIGURATION: '待自动配置',
  STOPPED: '当前已停止',
  RUNNING: '当前正在运行',
  ERROR: '运行异常',
}

function runtimeLabel(source: PersonalSourceView): string {
  return runtimeLabels[source.runtime_state]
}

async function setDesiredEnabled(source: PersonalSourceView): Promise<void> {
  if (busySourceIds.value.includes(source.id)) return
  busySourceIds.value = [...busySourceIds.value, source.id]
  actionError.value = null
  actionMessage.value = null
  try {
    const updated = await $fetch<PersonalSourceView>(`/api/v1/sources/${source.id}`, {
      method: 'PATCH',
      body: { desired_enabled: !source.desired_enabled },
      retry: 0,
      timeout: 5_000,
    })
    sources.value = sources.value.map(item => item.id === updated.id ? updated : item)
    actionMessage.value = updated.desired_enabled
      ? `已记录启用 ${updated.display_name} 的意图；运行状态仍由系统事实决定。`
      : `已手工停用 ${updated.display_name}。`
  }
  catch {
    actionError.value = '来源状态保存失败，服务端原状态未被页面覆盖。'
  }
  finally {
    busySourceIds.value = busySourceIds.value.filter(id => id !== source.id)
  }
}
</script>

<template>
  <section class="personal-sources-page" aria-labelledby="personal-sources-title">
    <header class="personal-sources-header">
      <div>
        <p class="personal-sources-eyebrow">个人研究模式</p>
        <h1 id="personal-sources-title">我的来源</h1>
        <p>启停表示你的研究意图；运行状态来自系统实际状态，两者不会互相冒充。</p>
      </div>
      <button class="secondary-button" type="button" :disabled="status === 'pending'" @click="refresh()">
        刷新状态
      </button>
    </header>

    <p v-if="actionMessage" class="success" role="status">{{ actionMessage }}</p>
    <p v-if="actionError" class="problem" role="alert">{{ actionError }}</p>
    <div v-if="error" class="problem" role="alert">
      来源列表加载失败，请确认本地服务和 Owner 身份可用。
      <button type="button" @click="refresh()">重试</button>
    </div>
    <p v-else-if="status === 'pending'" class="loading" aria-live="polite">正在读取来源…</p>
    <p v-else-if="sources.length === 0" class="empty-state">当前还没有来源。</p>

    <div v-else class="source-list" aria-label="个人来源列表">
      <article v-for="source in sources" :key="source.id" class="source-card">
        <div class="source-identity">
          <h2>{{ source.display_name }}</h2>
          <a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.url }}</a>
        </div>
        <dl class="source-states">
          <div>
            <dt>用户启停状态</dt>
            <dd :class="source.desired_enabled ? 'intent-enabled' : 'intent-disabled'">
              {{ source.desired_enabled ? '用户已启用' : '用户已停用' }}
            </dd>
          </div>
          <div>
            <dt>运行状态</dt>
            <dd>{{ runtimeLabel(source) }}</dd>
          </div>
        </dl>
        <button
          class="source-switch"
          type="button"
          role="switch"
          :aria-checked="source.desired_enabled"
          :aria-label="`${source.desired_enabled ? '停用' : '启用'}${source.display_name}`"
          :disabled="busySourceIds.includes(source.id)"
          @click="setDesiredEnabled(source)"
        >
          <span aria-hidden="true" class="source-switch__track">
            <span class="source-switch__thumb" />
          </span>
          {{ busySourceIds.includes(source.id) ? '正在保存…' : source.desired_enabled ? '停用' : '启用' }}
        </button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.personal-sources-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.personal-sources-header,
.source-card,
.source-states,
.source-states div {
  display: grid;
}

.personal-sources-header {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--spacing-4);
}

.personal-sources-header h1,
.personal-sources-header p,
.source-card h2,
.source-card dl {
  margin: 0;
}

.personal-sources-eyebrow {
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.personal-sources-header h1 {
  margin-block: var(--spacing-1);
  color: var(--color-ink-900);
}

.personal-sources-header div > p:last-child,
.source-identity a,
.source-states dt {
  color: var(--color-ink-600);
}

.source-list {
  display: grid;
  gap: var(--spacing-3);
}

.source-card {
  grid-template-columns: minmax(16rem, 1.4fr) minmax(18rem, 1fr) auto;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-4);
}

.source-identity {
  min-width: 0;
}

.source-identity h2 {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
}

.source-identity a {
  display: block;
  overflow: hidden;
  margin-top: var(--spacing-1);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-states {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-3);
}

.source-states div {
  gap: var(--spacing-1);
}

.source-states dt {
  font-size: var(--text-xs);
}

.source-states dd {
  margin: 0;
  color: var(--color-ink-900);
  font-weight: var(--font-weight-semibold);
}

.intent-enabled {
  color: var(--color-verified-700) !important;
}

.intent-disabled {
  color: var(--color-ink-600) !important;
}

.source-switch,
.secondary-button {
  display: inline-flex;
  min-height: var(--spacing-10);
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-brand-700);
  background: var(--color-surface);
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  gap: var(--spacing-2);
}

.source-switch__track {
  display: inline-flex;
  width: var(--spacing-8);
  height: var(--spacing-4);
  align-items: center;
  padding: 2px;
  background: var(--color-ink-300);
  border-radius: var(--radius-pill);
}

.source-switch__thumb {
  width: calc(var(--spacing-4) - 4px);
  height: calc(var(--spacing-4) - 4px);
  background: var(--color-surface);
  border-radius: var(--radius-pill);
  transition: transform 120ms ease;
}

.source-switch[aria-checked='true'] .source-switch__track {
  background: var(--color-brand-700);
}

.source-switch[aria-checked='true'] .source-switch__thumb {
  transform: translateX(var(--spacing-4));
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.problem,
.success,
.empty-state,
.loading {
  margin: 0;
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-sm);
}

.problem {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid currentColor;
}

.success {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
  border: 1px solid currentColor;
}

.empty-state,
.loading {
  color: var(--color-ink-600);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

@media (max-width: 63.999rem) {
  .source-card {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .source-states {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}

@media (max-width: 47.999rem) {
  .personal-sources-header,
  .source-card,
  .source-states {
    grid-template-columns: 1fr;
  }

  .personal-sources-header {
    align-items: stretch;
  }

  .source-states,
  .source-switch {
    grid-column: 1;
  }

  .source-switch {
    width: 100%;
  }
}
</style>
