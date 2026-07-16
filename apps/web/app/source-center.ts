import type {
  ConnectorConfigPreview,
  ConnectorConfigPreviewRequest,
  ConnectorConfigVersionView as CanonicalConnectorConfigVersionView,
  ConnectorDefinitionView as CanonicalConnectorDefinitionView,
  ConnectorType,
  ReviewEvidence,
  RuntimeAuthorization as CanonicalRuntimeAuthorization,
  SourceAssessmentSubmission,
  SourceAuditEventView as CanonicalSourceAuditEventView,
  SourceAuthorityAssessment,
  SourceCoverageCell as CanonicalSourceCoverageCell,
  SourceCoverageMatrix,
  SourceDetail,
  SourceIndependenceAssessment,
  SourceLifecycleAction as CanonicalSourceLifecycleAction,
  SourceLifecycleEventView as CanonicalSourceLifecycleEventView,
  SourceLifecycleState as CanonicalSourceLifecycleState,
  SourcePolicyV2Submission,
  SourcePolicyVersionView as CanonicalSourcePolicyVersionView,
  SourceSummary,
  SourceTrialQualitySummary as CanonicalSourceTrialQualitySummary,
  SourceTrialRunView as CanonicalSourceTrialRunView,
} from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'

export type SourceLifecycleState = CanonicalSourceLifecycleState

export type SourceLifecycleDisplayState = SourceLifecycleState | 'UNKNOWN'

export type RuntimeAuthorization = CanonicalRuntimeAuthorization

export type SourceLifecycleAction = CanonicalSourceLifecycleAction

export type SourceAssessmentView = SourceAuthorityAssessment | SourceIndependenceAssessment
export type SourceAssessmentPayload = SourceAssessmentSubmission

export type SourceCenterSummary = SourceSummary

export type SourceCenterDetail = SourceDetail

export type SourcePolicyVersionView = Omit<
  CanonicalSourcePolicyVersionView,
  'document'
> & {
  readonly document: SourcePolicyDocument
}

export type SourceReviewEvidenceView = ReviewEvidence

export type SourcePolicyDocument = Omit<
  SourcePolicyV2Submission,
  'policy_version' | 'reason' | 'schema_version' | 'valid_from' | 'valid_until'
>

export type ConnectorDefinitionView = CanonicalConnectorDefinitionView

export interface ConnectorDefinitionOption {
  readonly connectorType: ConnectorKind
  readonly definitionVersion: string
  readonly label: string
}

export type ConnectorKind = ConnectorType

export type DeclarativeConnectorPayload = ConnectorConfigPreviewRequest

export type ConnectorConfigVersionView = CanonicalConnectorConfigVersionView

export type ConnectorPreviewResult = ConnectorConfigPreview

export type SourceTrialRunView = CanonicalSourceTrialRunView

export type SourceTrialQualitySummary = CanonicalSourceTrialQualitySummary

export type SourceLifecycleEventView = CanonicalSourceLifecycleEventView

export type SourceAuditEventView = CanonicalSourceAuditEventView

export type SourceCoverageCell = CanonicalSourceCoverageCell

export type SourceCoverageResponse = SourceCoverageMatrix

export interface SafeConnectorConfigRow {
  readonly label: string
  readonly value: string
}

export interface SourceSloPayloadInput {
  readonly applicability: string
  readonly authorizationConfirmed: boolean
  readonly reason: string
  readonly targetMinutes: number | ''
  readonly technicalConditionsConfirmed: boolean
}

const SHANGHAI_UTC_OFFSET_MILLISECONDS = 8 * 60 * 60 * 1_000
const localDateTimePattern
  = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/

/** Convert an HTML datetime-local value using the product's fixed Asia/Shanghai zone. */
export function shanghaiLocalDateTimeToUtc(value: string): string {
  const match = localDateTimePattern.exec(value)
  if (!match) throw new Error('invalid Asia/Shanghai local date-time')

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = Number(match[6] ?? '0')
  if (![year, month, day, hour, minute, second].every(Number.isInteger)) {
    throw new Error('invalid Asia/Shanghai local date-time')
  }
  const localAsUtc = Date.UTC(year, month - 1, day, hour, minute, second)
  const normalized = new Date(localAsUtc)
  if (
    year < 1_000
    || normalized.getUTCFullYear() !== year
    || normalized.getUTCMonth() !== month - 1
    || normalized.getUTCDate() !== day
    || normalized.getUTCHours() !== hour
    || normalized.getUTCMinutes() !== minute
    || normalized.getUTCSeconds() !== second
  ) throw new Error('invalid Asia/Shanghai local date-time')

  return new Date(localAsUtc - SHANGHAI_UTC_OFFSET_MILLISECONDS).toISOString()
}

export type SourceSloPayload
  = | {
    readonly applicability: 'APPLICABLE'
    readonly authorization_confirmed: true
    readonly target_minutes: number
    readonly technical_conditions_confirmed: true
  }
    | {
      readonly applicability: 'NOT_APPLICABLE'
      readonly authorization_confirmed: false
      readonly reason: string
      readonly technical_conditions_confirmed: false
    }

export function sourceSloPayload(input: SourceSloPayloadInput): SourceSloPayload | null {
  if (input.applicability === 'APPLICABLE') {
    if (
      !input.authorizationConfirmed
      || !input.technicalConditionsConfirmed
      || typeof input.targetMinutes !== 'number'
      || !Number.isInteger(input.targetMinutes)
      || input.targetMinutes < 1
      || input.targetMinutes > 10_080
    ) return null
    return {
      applicability: 'APPLICABLE',
      authorization_confirmed: true,
      target_minutes: input.targetMinutes,
      technical_conditions_confirmed: true,
    }
  }
  const reason = input.reason.trim()
  if (input.applicability !== 'NOT_APPLICABLE' || !reason) return null
  return {
    applicability: 'NOT_APPLICABLE',
    authorization_confirmed: false,
    reason,
    technical_conditions_confirmed: false,
  }
}

const sensitiveConfigKey = /(?:credential|secret|token|password|passwd|cookie|authorization|api[_-]?key|private[_-]?key)/i
const sensitiveConfigValue = /(?:vault:\/\/|\bbearer\s+|\bbasic\s+|(?:password|token|secret|api[_-]?key)=)/i

function scalarDisplayValue(value: unknown): string | null {
  if (typeof value === 'string') return sensitiveConfigValue.test(value) ? null : value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value === null) return '—'
  return null
}

/** Defensive read projection. Server redaction remains authoritative. */
export function safeConnectorConfigRows(
  config: Readonly<Record<string, unknown>>,
): readonly SafeConnectorConfigRow[] {
  const rows: SafeConnectorConfigRow[] = []

  function append(value: unknown, path: string, depth: number): void {
    if (rows.length >= 100 || depth > 4) return
    const scalar = scalarDisplayValue(value)
    if (scalar !== null) {
      rows.push({ label: path, value: scalar })
      return
    }
    if (Array.isArray(value)) {
      const values = value.map(scalarDisplayValue)
      if (values.every(item => item !== null)) {
        rows.push({ label: path, value: values.join(' / ') })
      }
      return
    }
    if (typeof value !== 'object' || value === null) return
    for (const [key, child] of Object.entries(value)) {
      if (sensitiveConfigKey.test(key)) continue
      append(child, path ? `${path}.${key}` : key, depth + 1)
    }
  }

  for (const [key, value] of Object.entries(config)) {
    if (sensitiveConfigKey.test(key)) continue
    append(value, key, 0)
  }
  return rows
}

const lifecycleLabels: Readonly<Record<SourceLifecycleDisplayState, string>> = {
  ACTIVE: '已激活',
  CANDIDATE: '候选',
  COMPLIANCE_REVIEW: '合规复核',
  PAUSED: '已暂停',
  RETIRED: '已退役',
  TRIAL: '试运行',
  UNKNOWN: '权威状态不可用',
}

export function lifecycleStateOf(source: SourceCenterSummary): SourceLifecycleDisplayState {
  return source.lifecycle_state ?? 'UNKNOWN'
}

export function lifecycleLabel(source: SourceCenterSummary): string {
  return lifecycleLabels[lifecycleStateOf(source)]
}

export function lifecycleTone(source: SourceCenterSummary): StatusBadgeTone {
  const state = lifecycleStateOf(source)
  if (state === 'ACTIVE') return 'healthy'
  if (state === 'PAUSED' || state === 'RETIRED' || state === 'UNKNOWN') return 'conflict'
  if (state === 'TRIAL' || state === 'COMPLIANCE_REVIEW') return 'info'
  return 'pending'
}

export function runtimeAuthorizationOf(source: SourceCenterSummary): RuntimeAuthorization {
  return source.runtime_authorization ?? 'DENIED'
}

export function runtimeAuthorizationLabel(source: SourceCenterSummary): string {
  const authorization = runtimeAuthorizationOf(source)
  if (authorization === 'PRODUCTION') return '生产已授权'
  if (authorization === 'TRIAL_ONLY') return '仅试运行'
  return '生产拒绝'
}

export function runtimeAuthorizationTone(source: SourceCenterSummary): StatusBadgeTone {
  const authorization = runtimeAuthorizationOf(source)
  if (authorization === 'PRODUCTION') return 'verified'
  if (authorization === 'TRIAL_ONLY') return 'info'
  return 'pending'
}

export function formatShanghaiDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Shanghai',
  }).format(date)
}

export function apiProblemMessage(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '请求失败，请稍后重试。'
  const data = 'data' in value ? value.data : undefined
  if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') {
    return data.detail
  }
  if ('message' in value && typeof value.message === 'string') return value.message
  return '请求失败，请检查治理证据和服务状态。'
}
