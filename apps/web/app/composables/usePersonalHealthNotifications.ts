import type { PersonalSourceStreamView, PersonalSourceView } from '@srbg/contracts'
import type { Ref } from 'vue'

const NOTIFIED_STORAGE_KEY = 'srbg:personal-health:notified:v1'
const MAX_NOTIFIED_IDS = 100

type HealthSignature = string

export function healthSignature(stream: PersonalSourceStreamView): HealthSignature {
  return [
    stream.status,
    stream.health_status ?? 'UNKNOWN',
    stream.health_reason ?? 'NONE',
    stream.runtime_state ?? 'STOPPED',
  ].join('|')
}

function signatureIsActionable(signature: HealthSignature): boolean {
  return signature.includes('PROBE_FAILED')
    || signature.includes('|DEGRADED|')
    || signature.includes('|UNHEALTHY|')
    || signature.includes('|CIRCUIT_OPEN')
    || signature.includes('|BUDGET_EXHAUSTED')
    || signature.includes('|INACCESSIBLE')
}

export function shouldNotifyTransition(
  previous: HealthSignature | null,
  current: HealthSignature,
): boolean {
  return previous !== null
    && previous !== current
    && (signatureIsActionable(previous) || signatureIsActionable(current))
}

export function actionableSourceCount(sources: readonly PersonalSourceView[]): number {
  return sources.filter(source => source.desired_enabled && (source.streams ?? []).some(stream =>
    signatureIsActionable(healthSignature(stream)),
  )).length
}

function reasonLabel(stream: PersonalSourceStreamView): string {
  const labels: Readonly<Record<string, string>> = {
    BUDGET_EXHAUSTED: '预算暂停',
    CIRCUIT_OPEN: '熔断中',
    CONTENT_STALE: '内容长时间未更新',
    DNS_FAILURE: 'DNS 解析失败',
    HTTP_429: '请求过于频繁',
    HTTP_5XX: '来源服务异常',
    PARSE_FAILED: '解析失败',
    STRUCTURE_CHANGED: '页面结构发生变化',
    TIMEOUT: '请求超时',
  }
  if (!signatureIsActionable(healthSignature(stream))) return '健康已恢复'
  return labels[stream.health_reason ?? '']
    ?? (stream.status === 'PROBE_FAILED' ? '配置失败' : '来源健康异常')
}

function readNotifiedIds(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(NOTIFIED_STORAGE_KEY) ?? '[]') as unknown
    return Array.isArray(value) ? value.filter(item => typeof item === 'string').slice(-MAX_NOTIFIED_IDS) : []
  }
  catch {
    return []
  }
}

function rememberNotification(id: string): boolean {
  const current = readNotifiedIds()
  if (current.includes(id)) return false
  localStorage.setItem(
    NOTIFIED_STORAGE_KEY,
    JSON.stringify([...current, id].slice(-MAX_NOTIFIED_IDS)),
  )
  return true
}

export function usePersonalHealthNotifications(
  sources: Ref<PersonalSourceView[]>,
  refresh: () => Promise<unknown>,
) {
  const permission = ref<NotificationPermission>('default')
  const supported = ref(false)
  const previous = new Map<string, HealthSignature>()
  let initialized = false
  let pollTimer: ReturnType<typeof setInterval> | undefined

  function processSnapshot(values: readonly PersonalSourceView[]): void {
    const currentStreamIds = new Set<string>()
    for (const source of values) {
      for (const stream of source.streams ?? []) {
        currentStreamIds.add(stream.id)
        const signature = healthSignature(stream)
        const old = previous.get(stream.id) ?? null
        previous.set(stream.id, signature)
        if (!initialized || !source.desired_enabled || !shouldNotifyTransition(old, signature)) continue
        const observationId = stream.health_observation_id
          ?? `${stream.id}:${stream.health_observed_at ?? signature}`
        if (permission.value !== 'granted' || !rememberNotification(observationId)) continue
        const notification = new Notification('来源健康状态变化', {
          body: `${source.display_name}：${reasonLabel(stream)}`,
          tag: `source-health:${stream.id}`,
        })
        notification.onclick = () => window.focus()
      }
    }
    for (const id of previous.keys()) {
      if (!currentStreamIds.has(id)) previous.delete(id)
    }
    initialized = true
  }

  async function requestPermission(): Promise<void> {
    if (!supported.value || permission.value === 'denied') return
    permission.value = await Notification.requestPermission()
  }

  watch(sources, values => processSnapshot(values), { deep: true, immediate: true })

  onMounted(() => {
    supported.value = 'Notification' in window
    permission.value = supported.value ? Notification.permission : 'denied'
    pollTimer = setInterval(() => void refresh(), 30_000)
  })

  onBeforeUnmount(() => {
    if (pollTimer !== undefined) clearInterval(pollTimer)
  })

  return { permission, requestPermission, supported }
}
