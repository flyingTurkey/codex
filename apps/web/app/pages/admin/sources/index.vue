<script setup lang="ts">
import type { CreateSourceRequest, SourceDetail, SourceSummary } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { reactive, ref } from 'vue'

const drawerOpen = ref(false)
const submitting = ref(false)
const formError = ref<string | null>(null)
const form = reactive<CreateSourceRequest>({
  name: '',
  base_url: '',
  channel: 'BOTH',
  source_type: 'government',
  authority_level: 'A1',
  priority: 'P1',
  collection_method: 'manual_fixture',
  poll_interval_minutes: 60,
  owner: 'source_ops',
})

const {
  data: sources,
  error,
  refresh,
  status,
} = await useFetch<SourceSummary[]>('/api/v1/admin/sources', {
  default: () => [],
  retry: 0,
  timeout: 5_000,
})

const stateLabels: Readonly<Record<SourceSummary['state'], string>> = {
  CANDIDATE: '候选',
  COMPLIANCE_REVIEW: '合规复核',
  FIXTURE_TEST: '样本测试',
  APPROVED: '已批准',
  ACTIVE: '已激活',
}

function toneFor(source: SourceSummary): StatusBadgeTone {
  if (source.effective_active) return 'healthy'
  if (source.state === 'ACTIVE' && !source.effective_active) return 'conflict'
  return source.state === 'CANDIDATE' ? 'pending' : 'info'
}

function apiMessage(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '请求失败，请稍后重试。'
  const data = 'data' in value ? value.data : undefined
  if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') {
    return data.detail
  }
  return '请求失败，请检查输入和服务状态。'
}

async function submitSource(): Promise<void> {
  submitting.value = true
  formError.value = null
  try {
    const created = await $fetch<SourceDetail>('/api/v1/admin/sources', {
      method: 'POST',
      body: form,
      timeout: 5_000,
    })
    drawerOpen.value = false
    await refresh()
    await navigateTo(`/admin/sources/${created.id}`)
  } catch (requestError) {
    formError.value = apiMessage(requestError)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="source-registry-page">
    <PageHeader
      title="来源注册与准入"
      eyebrow="来源管理"
      description="候选来源默认禁用；只有策略、证据、样本和人工准入全部通过后才可激活。"
    >
      <template #status>
        <StatusBadge tone="pending" label="默认拒绝" />
        <span>{{ sources.length }} 个已登记来源</span>
      </template>
      <template #actions>
        <button class="primary-button" type="button" @click="drawerOpen = true">
          登记候选来源
        </button>
      </template>
    </PageHeader>

    <div v-if="error" class="problem" role="alert">
      来源列表暂不可用。系统没有用演示数据替代真实结果。
      <button type="button" @click="refresh()">重试</button>
    </div>

    <div v-else-if="status === 'pending'" class="loading" aria-live="polite">正在读取来源…</div>

    <EmptyState
      v-else-if="sources.length === 0"
      title="还没有登记来源"
      description="登记后来源仍保持 CANDIDATE / disabled，完成准入证据前不会进入采集。"
      icon="Database"
    >
      <template #actions>
        <button class="secondary-button" type="button" @click="drawerOpen = true">
          登记第一个来源
        </button>
      </template>
    </EmptyState>

    <div v-else class="source-list" aria-label="来源列表">
      <NuxtLink
        v-for="source in sources"
        :key="source.id"
        class="source-row"
        :to="`/admin/sources/${source.id}`"
      >
        <div class="source-row__identity">
          <span class="source-code">{{ source.registry_code ?? 'CUSTOM' }}</span>
          <strong>{{ source.name }}</strong>
          <span>{{ source.base_url }}</span>
        </div>
        <div class="source-row__meta">
          <span>{{ source.channel }}</span>
          <span>{{ source.authority_level }}</span>
          <span>{{ source.fixture_count }} 个样本</span>
        </div>
        <StatusBadge :tone="toneFor(source)" :label="stateLabels[source.state]" />
      </NuxtLink>
    </div>

    <ResponsiveDrawer
      v-model="drawerOpen"
      title="登记候选来源"
      description="状态和启用标记由服务端固定为 CANDIDATE / disabled。"
    >
      <form id="source-create-form" class="source-form" @submit.prevent="submitSource">
        <label>来源名称<input v-model.trim="form.name" required maxlength="200"></label>
        <label>来源 URL<input v-model.trim="form.base_url" required type="url" maxlength="2048"></label>
        <label>
          情报频道
          <select v-model="form.channel">
            <option value="BOTH">数字化与安全</option>
            <option value="DIGITAL">数字化</option>
            <option value="SAFETY">安全</option>
          </select>
        </label>
        <label>
          来源类型
          <select v-model="form.source_type">
            <option value="government">政府</option>
            <option value="standards">标准平台</option>
            <option value="research_institute">科研机构</option>
            <option value="association">协会</option>
            <option value="journal">期刊</option>
            <option value="enterprise">企业</option>
            <option value="media">媒体</option>
            <option value="academic_api">学术 API</option>
            <option value="academic_database">学术数据库</option>
          </select>
        </label>
        <div class="field-grid">
          <label>权威等级<select v-model="form.authority_level"><option v-for="level in ['A0', 'A1', 'B1', 'B2', 'C1', 'C2']" :key="level" :value="level">{{ level }}</option></select></label>
          <label>优先级<select v-model="form.priority"><option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option></select></label>
        </div>
        <label>接入方式<input v-model.trim="form.collection_method" required maxlength="50"></label>
        <label>轮询间隔（分钟）<input v-model.number="form.poll_interval_minutes" required type="number" min="1" max="10080"></label>
        <label>负责人<input v-model.trim="form.owner" required maxlength="100"></label>
        <p v-if="formError" class="problem" role="alert">{{ formError }}</p>
      </form>
      <template #footer>
        <div class="drawer-actions">
          <button class="secondary-button" type="button" @click="drawerOpen = false">取消</button>
          <button class="primary-button" type="submit" form="source-create-form" :disabled="submitting">
            {{ submitting ? '正在登记…' : '登记候选来源' }}
          </button>
        </div>
      </template>
    </ResponsiveDrawer>
  </section>
</template>

<style scoped>
.source-registry-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.source-list {
  display: grid;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.source-row {
  display: grid;
  grid-template-columns: minmax(16rem, 1fr) auto auto;
  align-items: center;
  gap: var(--spacing-5);
  padding: var(--spacing-4) var(--spacing-5);
  text-decoration: none;
  border-bottom: 1px solid var(--color-border);
}

.source-row:last-child { border-bottom: 0; }
.source-row:hover { background: var(--color-surfaceMuted); }

.source-row__identity,
.source-row__meta {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.source-row__identity > span:last-child {
  overflow: hidden;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-row__meta {
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.source-code {
  color: var(--color-brand-700);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
}

.source-form { display: grid; gap: var(--spacing-4); }
.source-form label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); }
.source-form input,
.source-form select { width: 100%; min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-ink-900); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-3); }
.drawer-actions { display: flex; justify-content: flex-end; gap: var(--spacing-2); }
.primary-button,
.secondary-button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-4); font-weight: var(--font-weight-semibold); border: 1px solid var(--color-brand-700); border-radius: var(--radius-sm); cursor: pointer; }
.primary-button { color: var(--color-surface); background: var(--color-brand-700); }
.secondary-button { color: var(--color-brand-700); background: var(--color-surface); }
.primary-button:disabled { cursor: wait; opacity: 0.6; }
.problem { margin: 0; padding: var(--spacing-3); color: var(--color-conflict-700); background: var(--color-conflict-50); border: 1px solid currentColor; border-radius: var(--radius-sm); }
.loading { padding: var(--spacing-8); color: var(--color-ink-600); text-align: center; }

@media (max-width: 60rem) {
  .source-row { grid-template-columns: 1fr auto; }
  .source-row__meta { grid-column: 1 / -1; }
}

@media (max-width: 40rem) {
  .source-row { grid-template-columns: 1fr; }
  .field-grid { grid-template-columns: 1fr; }
}
</style>
