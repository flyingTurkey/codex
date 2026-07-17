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
const newUrl = ref('')
const addingUrl = ref(false)
const reprobeSourceIds = ref<string[]>([])
let probePollTimer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  probePollTimer = setInterval(() => {
    const probeActive = sources.value.some(source =>
      source.latest_probe_run?.status === 'QUEUED'
      || source.latest_probe_run?.status === 'RUNNING',
    )
    if (probeActive && status.value !== 'pending') void refresh()
  }, 2_000)
})

onBeforeUnmount(() => {
  if (probePollTimer !== undefined) clearInterval(probePollTimer)
})

const runtimeLabels: Readonly<Record<PersonalSourceView['runtime_state'], string>> = {
  PENDING_CONFIGURATION: '待自动配置',
  STOPPED: '当前已停止',
  RUNNING: '当前正在运行',
  ERROR: '运行异常',
}

function runtimeLabel(source: PersonalSourceView): string {
  return runtimeLabels[source.runtime_state]
}

const streamTypeLabels = {
  UNKNOWN: '识别中',
  RSS_ATOM: 'RSS / Atom',
  SITEMAP: 'Sitemap',
  JSON_API: 'JSON API',
  DIRECT_PDF: '直接 PDF',
  LIST_DETAIL: '公开列表页',
} as const

const streamStatusLabels = {
  PROBING: '探测中',
  READY: '已就绪',
  PROBE_FAILED: '探测失败',
} as const

const healthLabels = {
  UNKNOWN: '尚无健康数据',
  HEALTHY: '健康',
  DEGRADED: '需要关注',
  UNHEALTHY: '异常',
} as const

const healthReasonLabels: Readonly<Record<string, string>> = {
  DNS_FAILURE: 'DNS 解析失败', TLS_FAILURE: 'TLS 连接失败', TIMEOUT: '请求超时',
  HTTP_401: 'HTTP 401：需要登录', HTTP_403: 'HTTP 403：禁止访问',
  HTTP_404: 'HTTP 404：入口不存在', HTTP_429: 'HTTP 429：请求过于频繁',
  HTTP_5XX: '来源服务异常', ROBOTS_BLOCKED: 'robots.txt 禁止访问',
  LOGIN_REQUIRED: '需要登录，系统不会绕过', CAPTCHA_DETECTED: '检测到验证码，系统不会绕过',
  PAYWALL_DETECTED: '检测到付费墙，系统不会绕过', MIME_MISMATCH: '响应类型不符',
  PARSE_FAILED: '解析失败，原始证据已保留', ZERO_DISCOVERY_STREAK: '连续零发现',
  STRUCTURE_CHANGED: 'DOM 或结构发生变化', REQUIRED_FIELDS_MISSING: '必要字段缺失',
  CONTENT_STALE: '内容过期', BUDGET_EXHAUSTED: '预算已耗尽', CIRCUIT_OPEN: '熔断等待恢复',
}

function healthReason(reason: string | null | undefined): string {
  return reason ? (healthReasonLabels[reason] ?? reason) : '无异常'
}

function displayTime(value: string | null | undefined): string {
  if (!value) return '暂无'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value))
}

async function addUrl(): Promise<void> {
  if (!newUrl.value.trim() || addingUrl.value) return
  addingUrl.value = true
  actionError.value = null
  actionMessage.value = null
  try {
    const created = await $fetch<PersonalSourceView>('/api/v1/sources', {
      method: 'POST', body: { url: newUrl.value.trim() }, retry: 0, timeout: 5_000,
    })
    const existing = sources.value.findIndex(item => item.id === created.id)
    sources.value = existing < 0
      ? [created, ...sources.value]
      : sources.value.map(item => item.id === created.id ? created : item)
    newUrl.value = ''
    actionMessage.value = 'URL 已保存，正在执行安全探测。'
    await refresh()
  }
  catch {
    actionError.value = 'URL 保存失败。请确认它是无需登录的公开 HTTPS 地址后重试。'
  }
  finally {
    addingUrl.value = false
  }
}

async function reprobe(source: PersonalSourceView, streamId?: string): Promise<void> {
  if (reprobeSourceIds.value.includes(source.id)) return
  reprobeSourceIds.value = [...reprobeSourceIds.value, source.id]
  actionError.value = null
  actionMessage.value = null
  try {
    const updated = await $fetch<PersonalSourceView>(`/api/v1/sources/${source.id}/reprobe`, {
      method: 'POST', body: streamId ? { stream_id: streamId } : {}, retry: 0, timeout: 5_000,
    })
    sources.value = sources.value.map(item => item.id === updated.id ? updated : item)
    actionMessage.value = `已重新探测 ${updated.display_name}。`
    await refresh()
  }
  catch {
    actionError.value = '重新探测失败，原有健康入口未被覆盖。'
  }
  finally {
    reprobeSourceIds.value = reprobeSourceIds.value.filter(id => id !== source.id)
  }
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

    <form class="add-url" aria-label="添加公开来源 URL" @submit.prevent="addUrl">
      <label for="personal-source-url">添加 URL</label>
      <div>
        <input
          id="personal-source-url"
          v-model="newUrl"
          type="url"
          inputmode="url"
          autocomplete="url"
          placeholder="https://example.gov.cn/"
          required
          :disabled="addingUrl"
        >
        <button class="primary-button" type="submit" :disabled="addingUrl || !newUrl.trim()">
          {{ addingUrl ? '正在保存…' : '保存并探测' }}
        </button>
      </div>
      <p>只需粘贴公开 HTTPS 地址；系统会自动识别 RSS、Sitemap、API、PDF 或公开列表页。</p>
    </form>

    <div v-if="!error && status !== 'pending' && sources.length > 0" class="source-list" aria-label="个人来源列表">
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
        <section class="stream-list" :aria-label="`${source.display_name} 的采集入口`">
          <p v-if="source.latest_probe_run?.status === 'QUEUED' || source.latest_probe_run?.status === 'RUNNING'" class="probe-progress" aria-live="polite">
            探测中，请稍候…
          </p>
          <article v-for="stream in (source.streams ?? [])" :key="stream.id" class="stream-row">
            <div>
              <strong>{{ streamTypeLabels[stream.stream_type] }}</strong>
              <span :class="`stream-status stream-status--${stream.status.toLowerCase()}`">{{ streamStatusLabels[stream.status] }}</span>
            </div>
            <a :href="stream.normalized_url" target="_blank" rel="noopener noreferrer">{{ stream.normalized_url }}</a>
            <p v-if="stream.failure_reason" class="stream-failure">{{ stream.failure_reason }}</p>
            <dl class="stream-health">
              <div><dt>是否实际运行</dt><dd>{{ stream.actual_running ? '是' : '否' }}</dd></div>
              <div><dt>流级健康</dt><dd>{{ healthLabels[stream.health_status ?? 'UNKNOWN'] }}</dd></div>
              <div><dt>异常原因</dt><dd>{{ healthReason(stream.health_reason) }}</dd></div>
              <div><dt>连续失败次数</dt><dd>{{ stream.consecutive_failures }}</dd></div>
              <div><dt>下次自愈时间</dt><dd>{{ displayTime(stream.next_self_heal_at) }}</dd></div>
              <div><dt>最近成功抓取时间</dt><dd>{{ displayTime(stream.last_successful_fetch_at) }}</dd></div>
              <div><dt>最近发现内容时间</dt><dd>{{ displayTime(stream.last_content_discovered_at) }}</dd></div>
            </dl>
            <button
              v-if="stream.status === 'PROBE_FAILED'"
              class="secondary-button"
              type="button"
              :disabled="reprobeSourceIds.includes(source.id)"
              @click="reprobe(source, stream.id)"
            >重新探测</button>
          </article>
          <p v-if="source.latest_probe_run?.status === 'FAILED' && (source.streams ?? []).length === 0" class="stream-failure">
            {{ source.latest_probe_run.failure_reason || '探测失败，可稍后重试。' }}
          </p>
        </section>
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
        <button
          class="secondary-button"
          type="button"
          :disabled="reprobeSourceIds.includes(source.id)"
          @click="reprobe(source)"
        >{{ reprobeSourceIds.includes(source.id) ? '正在重试…' : '重新探测' }}</button>
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

.add-url {
  display: grid;
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-2);
}

.add-url label { color: var(--color-ink-900); font-weight: var(--font-weight-semibold); }
.add-url > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--spacing-2); }
.add-url input { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.add-url p { margin: 0; color: var(--color-ink-600); font-size: var(--text-sm); }
.primary-button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-4); color: var(--color-surface); background: var(--color-brand-700); border: 1px solid var(--color-brand-700); border-radius: var(--radius-sm); font-weight: var(--font-weight-semibold); }

.stream-list { display: grid; grid-column: 1 / -1; gap: var(--spacing-2); }
.stream-row { display: grid; padding: var(--spacing-3); background: var(--color-surface-muted); border: 1px solid var(--color-border); border-radius: var(--radius-sm); gap: var(--spacing-1); }
.stream-row > div { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-2); }
.stream-row a { overflow-wrap: anywhere; color: var(--color-brand-700); font-family: var(--font-mono); font-size: var(--text-xs); }
.stream-status { font-size: var(--text-xs); font-weight: var(--font-weight-semibold); }
.stream-status--ready { color: var(--color-verified-700); }
.stream-status--probe_failed, .stream-failure { color: var(--color-conflict-700); }
.probe-progress, .stream-failure { margin: 0; }
.stream-health { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); margin: 0; gap: var(--spacing-2); }
.stream-health div { display: grid; gap: var(--spacing-1); }
.stream-health dt { color: var(--color-ink-600); font-size: var(--text-xs); }
.stream-health dd { margin: 0; color: var(--color-ink-900); font-size: var(--text-sm); }

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
  .add-url > div { grid-template-columns: 1fr; }
}
</style>
