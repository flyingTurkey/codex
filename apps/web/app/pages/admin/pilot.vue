<script setup lang="ts">
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'
import { computed, onBeforeUnmount, reactive, ref } from 'vue'

type PilotState = 'PREPARING' | 'READY' | 'RUNNING' | 'COMPLETED' | 'BLOCKED'

interface PilotWindow {
  id: string
  roster_version: string
  metric_definition_version: string
  gold_definition_version: string
  baseline_commit: string
  config_version: string
  database_revision: string
  environment: 'PREPRODUCTION'
  duration_hours: 168
  source_count: number
  state: PilotState
  version: number
  prepared_at: string
  started_at: string | null
  ends_at: string | null
  blocker_codes: string[]
}

interface WorkSession {
  id: string
  task_id: string
  category: string
  version: number
  active_seconds: number | null
}

type OperatorTaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED'

interface OperatorTask {
  id: string
  window_id: string
  source_id: string | null
  category: string
  assigned_to: string
  status: OperatorTaskStatus
  version: number
  created_at: string
  started_at: string | null
  completed_at: string | null
}

type CorrectionReason =
  | 'TIMER_INTERRUPTED'
  | 'MISSED_STOP'
  | 'DUPLICATE_SESSION'
  | 'ADMINISTRATIVE_CORRECTION'

const candidateSourceCodesPendingLeoApproval = [
  'GOV-002', 'GOV-003', 'GOV-004', 'GOV-005', 'GOV-006',
  'GOV-007', 'GOV-014', 'GOV-015', 'GOV-016', 'GOV-017',
  'GOV-020', 'NRA-001', 'GOV-010', 'RES-004', 'GOV-008',
  'RES-001', 'ENT-005', 'ENT-006', 'ENT-007', 'ENT-008',
] as const

const form = reactive({
  baselineCommit: '',
  reason: '记录第17轮20来源候选清单；仍待LEO外部审批',
})
const startReason = ref('请求服务端重新核验外部审批并启动168小时真实观察窗口')
const resumeSourceCode = ref('')
const resumeReason = ref('批准新版本后恢复来源并创建独立观察段')
const completeReason = ref('168小时到期后核验20来源诚实状态并完成窗口')
const busy = ref(false)
const message = ref<string | null>(null)
const activeWork = ref<WorkSession | null>(null)
const lastStoppedWork = ref<WorkSession | null>(null)
const correctionSeconds = ref<number | null>(null)
const correctionReason = ref<CorrectionReason>('TIMER_INTERRUPTED')
const operatorTaskSourceId = ref('')
const operatorTaskCategory = ref('SOURCE_MAINTENANCE')
const operatorTaskReason = ref('由LEO向yinzi分配不含正文和网址的运营任务')
let workHeartbeatTimer: ReturnType<typeof setInterval> | null = null

const {
  data: windows,
  error,
  refresh,
  status,
} = await useFetch<PilotWindow[]>('/api/v1/admin/pilot-windows', {
  default: () => [],
  retry: 0,
  timeout: 5_000,
})

const latestWindow = computed(() => windows.value[0] ?? null)
const runningWindow = computed(() => windows.value.find(window => window.state === 'RUNNING') ?? null)

const {
  data: operatorTasks,
  refresh: refreshOperatorTasks,
} = await useFetch<OperatorTask[]>('/api/v1/admin/operator-tasks', {
  default: () => [],
  retry: 0,
  timeout: 5_000,
})

function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

async function prepareWindow(): Promise<void> {
  busy.value = true
  message.value = null
  try {
    await $fetch<PilotWindow>('/api/v1/admin/pilot-windows', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey('r17-prepare') },
      body: {
        roster_version: 'r17-sources-v0.1',
        metric_definition_version: 'phase2-round17-metrics-v1.0.0',
        gold_definition_version: 'phase2-round17-gold-v1.0.0',
        baseline_commit: form.baselineCommit,
        config_version: 'r17-sources-v0.1',
        database_revision: '0017b_round17_pilot',
        source_codes: candidateSourceCodesPendingLeoApproval,
        environment: 'PREPRODUCTION',
        duration_hours: 168,
        reason: form.reason,
      },
      retry: 0,
      timeout: 10_000,
    })
    await refresh()
    message.value = '准备度快照已记录；该动作不会激活任何来源。'
  } catch {
    message.value = '准备失败：服务端未接受版本、来源或权限事实。'
  } finally {
    busy.value = false
  }
}

async function startWindow(window: PilotWindow): Promise<void> {
  busy.value = true
  message.value = null
  try {
    const result = await $fetch<PilotWindow>(
      `/api/v1/admin/pilot-windows/${window.id}/start`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('r17-start') },
        body: { expected_version: window.version, reason: startReason.value },
        retry: 0,
        timeout: 10_000,
      },
    )
    await refresh()
    message.value = result.state === 'RUNNING'
      ? '观察窗口已由服务端锁定为连续168小时。'
      : 'BLOCKED：仍有前置事实未满足，未启动真实观察。'
  } catch {
    message.value = 'BLOCKED：启动需要非本地OIDC、近期MFA及完整治理事实。'
  } finally {
    busy.value = false
  }
}

async function resumeSource(window: PilotWindow): Promise<void> {
  const sourceCode = resumeSourceCode.value.trim().toUpperCase()
  if (!/^[A-Z]{3}-[0-9]{3}$/.test(sourceCode)) return
  busy.value = true
  message.value = null
  try {
    await $fetch<PilotWindow>(
      `/api/v1/admin/pilot-windows/${window.id}/sources/${sourceCode}/resume`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('r17-resume') },
        body: { expected_version: window.version, reason: resumeReason.value },
        retry: 0,
        timeout: 10_000,
      },
    )
    resumeSourceCode.value = ''
    await refresh()
    message.value = '来源已按当前权威版本创建新的不可变观察段；旧段保持原样。'
  } catch {
    message.value = '恢复失败：仅LEO可在新策略、配置、计划、审批和事件化事实齐全后恢复。'
  } finally {
    busy.value = false
  }
}

async function completeWindow(window: PilotWindow): Promise<void> {
  busy.value = true
  message.value = null
  try {
    await $fetch<PilotWindow>(`/api/v1/admin/pilot-windows/${window.id}/complete`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey('r17-complete') },
      body: { expected_version: window.version, reason: completeReason.value },
      retry: 0,
      timeout: 10_000,
    })
    await refresh()
    message.value = '窗口已完成；观察段、时间戳和逐源状态保持不可变。'
  } catch {
    message.value = '完成失败：窗口尚未到期，或20来源仍缺诚实终态/当前权威事实。'
  } finally {
    busy.value = false
  }
}

async function createOperatorTask(): Promise<void> {
  if (!runningWindow.value) return
  busy.value = true
  message.value = null
  try {
    await $fetch<OperatorTask>('/api/v1/admin/operator-tasks', {
      method: 'POST',
      body: {
        window_id: runningWindow.value.id,
        source_id: operatorTaskSourceId.value.trim() || null,
        category: operatorTaskCategory.value,
        reason: operatorTaskReason.value,
      },
      retry: 0,
      timeout: 5_000,
    })
    operatorTaskSourceId.value = ''
    await refreshOperatorTasks()
    message.value = '运营任务已由LEO创建并唯一分配给yinzi。'
  } catch {
    message.value = '任务创建失败：仅经认证的LEO可在RUNNING窗口中分配任务。'
  } finally {
    busy.value = false
  }
}

async function completeOperatorTask(task: OperatorTask): Promise<void> {
  try {
    await $fetch<OperatorTask>(`/api/v1/admin/operator-tasks/${task.id}/complete`, {
      method: 'POST',
      body: {
        expected_version: task.version,
        reason: 'LEO确认yinzi已停止唯一计时会话并关闭任务',
      },
      retry: 0,
      timeout: 5_000,
    })
    await refreshOperatorTasks()
    message.value = '运营任务已由LEO关闭。'
  } catch {
    message.value = '任务关闭失败：必须先由yinzi完成有效计时并停止会话。'
  }
}

async function startWork(task: OperatorTask): Promise<void> {
  if (!runningWindow.value) {
    message.value = '计时器未启动：只有当前RUNNING观察窗口可以记录运营耗时。'
    return
  }
  try {
    activeWork.value = await $fetch<WorkSession>('/api/v1/admin/operator-work-sessions', {
      method: 'POST',
      body: { task_id: task.id },
      retry: 0,
      timeout: 5_000,
    })
    lastStoppedWork.value = null
    await refreshOperatorTasks()
    startWorkHeartbeat()
  } catch {
    message.value = '计时器未启动：必须使用非本地企业OIDC，且同一管理员只能有一个活动计时器。'
  }
}

function clearWorkHeartbeat(): void {
  if (workHeartbeatTimer === null) return
  clearInterval(workHeartbeatTimer)
  workHeartbeatTimer = null
}

function startWorkHeartbeat(): void {
  clearWorkHeartbeat()
  workHeartbeatTimer = setInterval(() => {
    void heartbeatWork()
  }, 60_000)
}

async function heartbeatWork(): Promise<void> {
  if (!activeWork.value) {
    clearWorkHeartbeat()
    return
  }
  const session = activeWork.value
  try {
    const heartbeat = await $fetch<WorkSession>(
      `/api/v1/admin/operator-work-sessions/${session.id}/heartbeat`,
      {
        method: 'POST',
        body: { expected_version: session.version },
        retry: 0,
        timeout: 5_000,
      },
    )
    if (activeWork.value?.id === session.id) activeWork.value = heartbeat
  } catch {
    clearWorkHeartbeat()
    message.value = '计时心跳失败，已停止本页自动续记；请刷新并核对服务端会话。'
  }
}

async function stopWork(): Promise<void> {
  if (!activeWork.value) return
  const session = activeWork.value
  clearWorkHeartbeat()
  try {
    const result = await $fetch<WorkSession>(
      `/api/v1/admin/operator-work-sessions/${session.id}/stop`,
      {
        method: 'POST',
        body: { expected_version: session.version },
        retry: 0,
        timeout: 5_000,
      },
    )
    activeWork.value = null
    lastStoppedWork.value = result
    correctionSeconds.value = result.active_seconds
    await refreshOperatorTasks()
    message.value = `本次有效处理时间 ${result.active_seconds ?? 0} 秒。`
  } catch {
    if (activeWork.value?.id === session.id) startWorkHeartbeat()
    message.value = '停止计时失败，请刷新后核对服务端状态。'
  }
}

async function correctWork(): Promise<void> {
  const session = lastStoppedWork.value
  if (!session || correctionSeconds.value === null) return
  try {
    const result = await $fetch<WorkSession>(
      `/api/v1/admin/operator-work-sessions/${session.id}/corrections`,
      {
        method: 'POST',
        body: {
          expected_version: session.version,
          active_seconds: correctionSeconds.value,
          reason_code: correctionReason.value,
        },
        retry: 0,
        timeout: 5_000,
      },
    )
    lastStoppedWork.value = result
    correctionSeconds.value = result.active_seconds
    message.value = `计时纠正已记录：${result.active_seconds ?? 0} 秒。`
  } catch {
    message.value = '计时纠正失败：数值不得超过真实会话时长，请刷新后核对版本。'
  }
}

onBeforeUnmount(clearWorkHeartbeat)
</script>

<template>
  <section class="pilot-page">
    <PageHeader
      eyebrow="第17轮 · 真实来源试运行"
      title="20来源观察门禁"
      description="只记录服务端权威ACTIVE来源、真实SCHEDULED运行和人工金标；回放、Fixture、回填及测试环境不会进入观察指标。"
    >
      <template #status>
        <StatusBadge
          :tone="latestWindow?.state === 'RUNNING' ? 'verified' : 'pending'"
          :label="latestWindow?.state ?? 'BLOCKED'"
        />
        <span>候选窗口 168 小时（待LEO确认）</span>
      </template>
    </PageHeader>

    <p v-if="message" class="notice" aria-live="polite">{{ message }}</p>
    <p v-if="error" class="problem" role="alert">无法读取服务端窗口事实；不会使用浏览器缓存替代。</p>

    <section class="panel" aria-labelledby="prepare-title">
      <div>
        <p class="eyebrow">T0 前</p>
        <h2 id="prepare-title">冻结基线与20来源队列</h2>
        <p>准备动作只形成可审计快照，不审批、不激活、不抓网。</p>
      </div>
      <form class="form" @submit.prevent="prepareWindow">
        <label>
          基线提交哈希
          <input
            v-model.trim="form.baselineCommit"
            required
            minlength="40"
            maxlength="40"
            pattern="[0-9a-f]{40}"
            autocomplete="off"
          >
        </label>
        <label>
          准备依据
          <textarea v-model.trim="form.reason" required maxlength="500" />
        </label>
        <button type="submit" :disabled="busy">记录准备度快照</button>
      </form>
      <details>
        <summary>查看候选清单，仍待LEO外部审批（{{ candidateSourceCodesPendingLeoApproval.length }}）</summary>
        <ul class="source-codes">
          <li v-for="code in candidateSourceCodesPendingLeoApproval" :key="code">{{ code }}</li>
        </ul>
      </details>
    </section>

    <section v-if="latestWindow" class="panel" aria-labelledby="window-title">
      <div class="window-heading">
        <div>
          <p class="eyebrow">最新权威窗口</p>
          <h2 id="window-title">{{ latestWindow.roster_version }}</h2>
        </div>
        <StatusBadge
          :tone="latestWindow.state === 'RUNNING' ? 'verified' : 'pending'"
          :label="latestWindow.state"
        />
      </div>
      <dl class="facts">
        <div><dt>来源</dt><dd>{{ latestWindow.source_count }} / 20</dd></div>
        <div><dt>数据库</dt><dd>{{ latestWindow.database_revision }}</dd></div>
        <div><dt>起点</dt><dd>{{ latestWindow.started_at ?? '尚未启动' }}</dd></div>
        <div><dt>终点</dt><dd>{{ latestWindow.ends_at ?? '尚未锁定' }}</dd></div>
      </dl>
      <div v-if="latestWindow.blocker_codes.length" class="blockers" role="status">
        <h3>BLOCKED</h3>
        <ul><li v-for="code in latestWindow.blocker_codes" :key="code">{{ code }}</li></ul>
      </div>
      <form
        v-if="latestWindow.state === 'READY' || latestWindow.state === 'BLOCKED'"
        class="start-row"
        @submit.prevent="startWindow(latestWindow)"
      >
        <label>启动依据<input v-model.trim="startReason" required maxlength="500"></label>
        <button type="submit" :disabled="busy">重新核验并启动</button>
      </form>
      <div v-if="latestWindow.state === 'RUNNING'" class="lifecycle-actions">
        <form class="form" @submit.prevent="resumeSource(latestWindow)">
          <h3>恢复已暂停来源</h3>
          <label>
            来源代码
            <input
              v-model.trim="resumeSourceCode"
              required
              pattern="[A-Za-z]{3}-[0-9]{3}"
              maxlength="7"
              autocomplete="off"
            >
          </label>
          <label>恢复依据<input v-model.trim="resumeReason" required maxlength="500"></label>
          <button type="submit" :disabled="busy">核验新版本并创建新段</button>
        </form>
        <form class="form" @submit.prevent="completeWindow(latestWindow)">
          <h3>完成到期窗口</h3>
          <label>完成依据<input v-model.trim="completeReason" required maxlength="500"></label>
          <button type="submit" :disabled="busy">核验20来源诚实状态并完成</button>
        </form>
      </div>
    </section>

    <EmptyState
      v-else-if="status !== 'pending'"
      title="尚无观察窗口"
      description="先提供真实基线提交，再由服务端核验20来源、OIDC身份、金标和指标版本。"
      icon="Database"
    />

    <section class="panel" aria-labelledby="work-title">
      <div>
        <p class="eyebrow">兼职管理员负荷</p>
        <h2 id="work-title">权威任务与无正文计时器</h2>
        <p>LEO创建和关闭任务，yinzi只能执行分配给自己的唯一会话。仅保存类别、时间和纠正记录，不保存正文、网址或敏感数据。</p>
      </div>
      <p v-if="!runningWindow" class="work-blocked" role="status">暂无RUNNING观察窗口，不能启动运营计时。</p>
      <form class="form" @submit.prevent="createOperatorTask">
        <h3>LEO任务控制</h3>
        <label>
          类别
          <select v-model="operatorTaskCategory" required>
            <option value="SOURCE_MAINTENANCE">来源维护</option>
            <option value="EXCEPTION_HANDLING">异常处理</option>
            <option value="R3_REVIEW">R3审核</option>
            <option value="COPYRIGHT_CORRECTION">版权/纠错</option>
          </select>
        </label>
        <label>
          来源UUID（可选）
          <input
            v-model.trim="operatorTaskSourceId"
            pattern="[0-9a-fA-F-]{36}"
            maxlength="36"
            autocomplete="off"
          >
        </label>
        <label>分配依据<input v-model.trim="operatorTaskReason" required maxlength="500"></label>
        <button type="submit" :disabled="!runningWindow || busy">创建并分配给yinzi</button>
      </form>
      <ul class="operator-tasks" aria-label="运营任务">
        <li v-for="task in operatorTasks" :key="task.id">
          <span>{{ task.category }} · {{ task.status }}</span>
          <span>{{ task.source_id ?? '跨来源' }}</span>
          <button
            v-if="task.status === 'PENDING' && !activeWork"
            type="button"
            :disabled="!runningWindow"
            @click="startWork(task)"
          >
            yinzi开始唯一会话
          </button>
          <button
            v-if="task.status === 'IN_PROGRESS' && activeWork?.task_id !== task.id"
            type="button"
            @click="completeOperatorTask(task)"
          >
            LEO关闭已停止任务
          </button>
        </li>
      </ul>
      <button v-if="activeWork" type="button" @click="stopWork">停止 {{ activeWork.category }} 计时</button>
      <form v-if="lastStoppedWork" class="form" @submit.prevent="correctWork">
        <h3>纠正最近一次计时</h3>
        <label>
          有效秒数
          <input v-model.number="correctionSeconds" type="number" min="0" max="43200" required>
        </label>
        <label>
          纠正原因代码
          <select v-model="correctionReason" required>
            <option value="TIMER_INTERRUPTED">计时中断</option>
            <option value="MISSED_STOP">忘记停止</option>
            <option value="DUPLICATE_SESSION">重复会话</option>
            <option value="ADMINISTRATIVE_CORRECTION">行政纠正</option>
          </select>
        </label>
        <button type="submit">保存纠正记录</button>
      </form>
    </section>
  </section>
</template>

<style scoped>
.pilot-page { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.panel { display: grid; gap: var(--spacing-4); padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.panel h2, .panel h3, .panel p { margin: 0; }
.eyebrow { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-weight-bold); letter-spacing: .08em; text-transform: uppercase; }
.form, .start-row { display: grid; gap: var(--spacing-3); }
.form label, .start-row label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-weight: var(--font-weight-semibold); }
input, textarea, select, button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
button { width: fit-content; color: var(--color-surface); background: var(--color-brand-700); font-weight: var(--font-weight-semibold); }
button:disabled { opacity: .55; }
.source-codes, .facts, .work-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--spacing-2); }
.source-codes { padding-left: var(--spacing-5); }
.facts { margin: 0; }
.facts div { padding: var(--spacing-3); background: var(--color-surfaceMuted); border-radius: var(--radius-sm); }
.facts dt { color: var(--color-ink-500); font-size: var(--text-xs); }
.facts dd { margin: var(--spacing-1) 0 0; overflow-wrap: anywhere; }
.window-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-3); }
.blockers, .problem, .notice { padding: var(--spacing-3); border-radius: var(--radius-sm); }
.blockers, .problem { color: var(--color-danger-700); background: var(--color-danger-50); }
.notice { color: var(--color-brand-900); background: var(--color-brand-50); }
.work-blocked { color: var(--color-ink-500); }
.operator-tasks { display: grid; gap: var(--spacing-2); margin: 0; padding: 0; list-style: none; }
.operator-tasks li { display: grid; grid-template-columns: 1fr 1fr auto; align-items: center; gap: var(--spacing-3); padding: var(--spacing-3); background: var(--color-surfaceMuted); border-radius: var(--radius-sm); }
.lifecycle-actions { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-4); }
@media (max-width: 48rem) { .source-codes, .facts, .work-actions { grid-template-columns: 1fr 1fr; } }
@media (max-width: 48rem) { .lifecycle-actions { grid-template-columns: 1fr; } }
@media (max-width: 48rem) { .operator-tasks li { grid-template-columns: 1fr; } }
</style>
