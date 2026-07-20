<script setup lang="ts">
import type {
  DigitalCaseTypeSummary,
  AiEquipmentTypeSummary,
  IotProductTypeSummary,
  ItemSummary,
  LowAltitudeEquipmentTypeSummary,
  PaperTypeSummary,
  SafetyCaseTypeSummary,
  SafetyRegulationTypeSummary,
  SoftwareProductTypeSummary,
} from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { StatusBadge } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import { safetyEngineeringLabel, safetyHazardLabel } from '../utils/safety-case-labels'
import ScoreBreakdownDrawer from './ScoreBreakdownDrawer.vue'
import { createUuidV7 } from '../utils/uuid-v7'
import type { V2CardItemExtras } from '../composables/useIntelligenceFeed'

const props = withDefaults(defineProps<{
  item: ItemSummary & V2CardItemExtras
  headingLevel?: 2 | 3
}>(), {
  headingLevel: 3,
})

const emit = defineEmits<{
  evidence: [itemId: string]
}>()
const scoreOpen = ref(false)
const saved = ref(Boolean(props.item.is_saved))
const saving = ref(false)
const saveProblem = ref<string | null>(null)
const feedback = ref<'USEFUL' | 'NOT_USEFUL' | null>(null)
const feedbackProblem = ref<string | null>(null)
watch(() => props.item.is_saved, value => { saved.value = Boolean(value) })

async function toggleSaved(): Promise<void> {
  if (saving.value) return
  saving.value = true
  saveProblem.value = null
  try {
    if (saved.value) {
      await $fetch(`/api/v1/saved-events/${props.item.id}`, { method: 'DELETE' })
      saved.value = false
    }
    else {
      await $fetch('/api/v1/saved-events', {
        method: 'POST',
        body: { event_id: props.item.id },
        headers: { 'Idempotency-Key': createUuidV7() },
      })
      saved.value = true
    }
  }
  catch {
    saveProblem.value = '收藏操作失败，请稍后重试。'
  }
  finally {
    saving.value = false
  }
}

async function recordFeedback(value: 'USEFUL' | 'NOT_USEFUL'): Promise<void> {
  feedbackProblem.value = null
  try {
    await $fetch('/api/v1/feedback', {
      method: 'POST',
      body: { event_id: props.item.id, value },
    })
    feedback.value = value
  }
  catch {
    feedbackProblem.value = '反馈提交失败，请稍后重试。'
  }
}

const shanghaiDateTime = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})

function formatDate(value: string | null): string {
  return value ? shanghaiDateTime.format(new Date(value)) : '发布时间待补充'
}

const documentStateLabels = {
  UPDATED: '已更新',
  RE_REVIEW_PENDING: '待复核',
  WITHDRAWN: '已撤回',
  SOURCE_UNAVAILABLE: '原文失效',
} as const

const documentStates = computed(() => {
  const states = [...(props.item.document_states ?? [])]
  if (props.item.publication_status === 'WITHDRAWN' && !states.includes('WITHDRAWN')) {
    states.push('WITHDRAWN')
  }
  return states
})
const isWithdrawn = computed(() => documentStates.value.includes('WITHDRAWN'))
const originalLinkLabel = computed(() => {
  if (isWithdrawn.value) return '查看撤回与存档信息'
  if (documentStates.value.includes('SOURCE_UNAVAILABLE')) return '原文失效，查看存档信息'
  return '查看官方原文'
})

const safetyCaseSummary = computed<SafetyCaseTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'SAFETY_CASE' ? summary : null
})

const regulationSummary = computed<SafetyRegulationTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'SAFETY_REGULATION' ? summary : null
})

const digitalSummary = computed<DigitalCaseTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'DIGITAL_CASE' ? summary : null
})
const paperSummary = computed<PaperTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'JOURNAL_PAPER' ? summary : null
})
type ProductTypeSummary = SoftwareProductTypeSummary | IotProductTypeSummary
  | LowAltitudeEquipmentTypeSummary | AiEquipmentTypeSummary
const productSummary = computed<ProductTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary && [
    'SOFTWARE_PRODUCT',
    'IOT_PRODUCT',
    'LOW_ALTITUDE_EQUIPMENT',
    'AI_EQUIPMENT',
  ].includes(summary.kind) ? summary as ProductTypeSummary : null
})
const headingTag = computed(() => `h${props.headingLevel}`)
const isAutomaticSignal = computed(() => Boolean(props.item.automatic_result_type))
const isUnverifiedAi = computed(() => props.item.automatic_result_type === 'UNVERIFIED_AI')
const isAiFailure = computed(() => props.item.automatic_result_type === 'AI_PROCESSING_FAILED')
const failureReasonLabels: Record<string, string> = {
  INVALID_JSON_OR_SCHEMA: '模型输出格式校验失败',
  PROMPT_INJECTION_RISK: '原文包含提示注入风险',
  MODEL_DISABLED: '模型当前不可用',
  PROVIDER_BALANCE_INSUFFICIENT: 'AI 预算或余额不可用',
  UNSUPPORTED_CLAIM: '存在无证据陈述',
  NUMBER_OR_DATE_CONFLICT: '数字或日期与证据冲突',
  LEGAL_RESPONSIBILITY_OR_CAUSAL_OVERREACH: '存在法律、责任或因果过度推断',
  ENTERPRISE_ATTRIBUTION_MISSING: '企业声明缺少归因',
  STALE_OR_SUPERSEDED_EVIDENCE: '使用了过期或已替代证据',
}

function failureReasonLabel(value: string): string {
  return failureReasonLabels[value] ?? value
}

const searchEvidenceFieldLabels = {
  TITLE: '标题',
  SOURCE: '来源',
  ACCEPTED_CLAIMS: 'Accepted claims',
  SOURCE_EXCERPT: '原文摘录',
} as const

const typeLabel = computed(() => {
  if (props.item.content_type === 'DIGITAL_CASE') return '数字化案例'
  if (props.item.content_type === 'JOURNAL_PAPER') return '期刊论文'
  if (props.item.content_type === 'SOFTWARE_PRODUCT') return '软件产品'
  if (props.item.content_type === 'IOT_PRODUCT') return '物联网产品'
  if (props.item.content_type === 'LOW_ALTITUDE_EQUIPMENT') return '低空设备'
  if (props.item.content_type === 'AI_EQUIPMENT') return 'AI 设备'
  if (props.item.content_type === 'SAFETY_CASE') return '安全案例'
  return '安全规定'
})

const maturityLabels: Record<string, string> = {
  CONCEPT: '概念',
  LAB_PROTOTYPE: '实验室原型',
  ENGINEERING_PROTOTYPE: '工程样机',
  PILOT: '试点',
  SINGLE_PROJECT_PRODUCTION: '单项目生产应用',
  MULTI_PROJECT_REPLICATION: '多项目复制',
  ENTERPRISE_SCALE: '企业规模应用',
  UNKNOWN: '成熟度未知',
}

const paperAccessLabels: Record<string, string> = {
  METADATA_ONLY: '仅题录',
  ABSTRACT_ALLOWED: '摘要可展示',
  OPEN_FULLTEXT: '开放全文入口',
}

const paperTypeLabels: Record<string, string> = {
  ARTICLE: '研究论文',
  REVIEW: '综述',
  METHOD: '方法论文',
  CASE_STUDY: '案例研究',
  OTHER: '其他',
  UNKNOWN: '类型待确认',
}

const scenarioLabels: Record<string, string> = {
  QUALITY_CONTROL: '质量控制',
  PROGRESS_CONTROL: '进度控制',
  INSPECTION: '巡检',
  STRUCTURAL_HEALTH_MONITORING: '结构健康监测',
  DECISION_SUPPORT: '决策支持',
  EQUIPMENT_MANAGEMENT: '设备管理',
}

const productEvidenceLabels: Record<string, string> = {
  VENDOR_CLAIM_ONLY: '仅厂商声明',
  PROJECT_EVIDENCE: '工程案例证据',
  RESEARCH_EVIDENCE: '研究证据',
  INDEPENDENT_VALIDATION: '独立验证',
  OFFICIAL_CERTIFICATION: '官方许可或认证',
  UNKNOWN: '证据等级未知',
}

const permitLabels: Record<string, string> = {
  UNKNOWN: '许可状态未知',
  NOT_REQUIRED: '无需许可',
  VERIFIED: '许可证据已核验',
}

const caseStatusMap = {
  CLOSED: { label: '已结案', tone: 'verified' },
  CORRECTED: { label: '已更正', tone: 'info' },
  ENFORCEMENT_DECISION: { label: '处罚问责', tone: 'verified' },
  FINAL_INVESTIGATION_REPORT: { label: '正式调查', tone: 'verified' },
  INITIAL_OFFICIAL_REPORT: { label: '官方初报', tone: 'pending' },
  RECTIFICATION_FOLLOW_UP: { label: '整改跟进', tone: 'pending' },
  UNDER_INVESTIGATION: { label: '调查中', tone: 'pending' },
  UNVERIFIED_LEAD: { label: '线索待核实', tone: 'conflict' },
  WITHDRAWN: { label: '已撤回', tone: 'withdrawn' },
} as const satisfies Record<
  NonNullable<SafetyCaseTypeSummary['incident_status']>,
  { label: string; tone: StatusBadgeTone }
>

const caseStatus = computed<{ label: string; tone: StatusBadgeTone } | null>(() => {
  const summary = safetyCaseSummary.value
  if (!summary?.incident_status) return null
  if (summary.incident_status === 'RECTIFICATION_FOLLOW_UP' && summary.rectification_has_open_issues) {
    return { label: '整改评估完成但仍有问题', tone: 'conflict' }
  }
  return caseStatusMap[summary.incident_status]
})

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

function formatLoss(amountMinor: number, currency: string): string {
  const major = Math.trunc(amountMinor / 100)
  const minor = amountMinor % 100
  const formattedMajor = new Intl.NumberFormat('zh-CN').format(major)
  const formattedMinor = minor === 0 ? '' : `.${String(minor).padStart(2, '0')}`
  return `${formattedMajor}${formattedMinor} ${currency === 'CNY' ? '人民币元' : currency}`
}
</script>

<template>
  <article
    class="intelligence-card"
    :class="{
      'is-unverified-ai': isUnverifiedAi,
      'is-ai-failure': isAiFailure,
      'is-ai-judgment': item.automatic_result_type === 'AI_JUDGMENT',
    }"
    :data-review-status="item.review_status"
    :data-result-type="item.automatic_result_type"
  >
    <div class="intelligence-card__meta">
      <span
        class="intelligence-card__type"
        :class="{
          'is-safety-case': item.content_type === 'SAFETY_CASE',
          'is-digital-case': item.content_type === 'DIGITAL_CASE',
          'is-paper': item.content_type === 'JOURNAL_PAPER',
          'is-product': productSummary,
        }"
      >
        {{ typeLabel }}
      </span>
      <span v-if="item.ai_assistance?.status === 'ASSISTED'" class="intelligence-card__badge is-ai">
        AI 辅助 · 已受控校验
      </span>
      <span v-else-if="item.ai_assistance?.status === 'DEGRADED'" class="intelligence-card__badge is-pending">
        无 AI · 题录降级
      </span>
      <span v-if="item.automatic_result_type === 'EVIDENCE_FACT'" class="intelligence-card__badge">
        证据事实
      </span>
      <span v-else-if="item.automatic_result_type === 'AI_JUDGMENT'" class="intelligence-card__badge is-ai">
        AI 判断（验证通过）
      </span>
      <span v-else-if="isUnverifiedAi" class="intelligence-card__badge is-pending">
        未验证 AI
      </span>
      <span v-else-if="isAiFailure" class="intelligence-card__badge is-pending">
        AI 处理失败
      </span>
      <span v-if="item.revision_state?.action === 'REVISE'" class="intelligence-card__badge">
        第 {{ item.revision_state.revision_number }} 版修订
      </span>
      <span v-if="item.revision_state?.action === 'REPUBLISH'" class="intelligence-card__badge is-reviewed">
        已重新发布
      </span>
      <span
        v-for="state in documentStates"
        :key="state"
        class="intelligence-card__badge is-document-state"
        :data-document-state="state"
      >
        {{ documentStateLabels[state] }}
      </span>
      <span v-if="paperSummary?.relation_status === 'RETRACTED'" data-testid="paper-retraction">
        <StatusBadge tone="withdrawn" label="已撤稿" />
      </span>
      <span v-else-if="paperSummary?.relation_status === 'CORRECTED'" data-testid="paper-correction">
        <StatusBadge tone="info" label="已有更正" />
      </span>
      <span v-if="isAutomaticSignal" class="intelligence-card__badge is-pending">
        机器整理 / 未人工复核
      </span>
      <span v-else-if="item.review_status === 'PENDING'" class="intelligence-card__badge is-pending">
        待人工审核
      </span>
      <template v-else>
        <span v-if="item.source_role" class="intelligence-card__badge">
          {{ item.source_role }}
        </span>
        <span class="intelligence-card__badge is-reviewed">已人工复核</span>
      </template>
      <span v-if="caseStatus" data-testid="case-status">
        <StatusBadge :tone="caseStatus.tone" :label="caseStatus.label" />
      </span>
      <span
        v-if="safetyCaseSummary?.conflicted_fields?.length"
        data-testid="case-conflict"
      >
        <StatusBadge tone="conflict" label="冲突待核实" />
      </span>
    </div>

    <component :is="headingTag" class="intelligence-card__title">
      <a :href="`/events/${item.id}`">{{ item.title }}</a>
    </component>

    <dl class="intelligence-card__source">
      <div>
        <dt>来源</dt>
        <dd>{{ item.source_name }}</dd>
      </div>
      <div>
        <dt>原文发布时间</dt>
        <dd>{{ formatDate(item.source_published_at) }}</dd>
      </div>
    </dl>

    <p
      v-if="item.search_context?.match_kind === 'EXACT_IDENTIFIER'"
      class="intelligence-card__search-match"
    >
      <strong>精确编号命中</strong>
      {{ (item.search_context.matched_identifiers ?? []).join('、') }}
    </p>
    <p v-else-if="item.search_context" class="intelligence-card__search-match">
      <strong>{{ item.search_context.match_kind === 'SEMANTIC' ? '语义召回' : '关键词命中' }}</strong>
      {{ (item.search_context.matched_fields ?? []).join('、') }}
    </p>
    <p v-if="item.search_explanation" class="intelligence-card__search-match">
      <span v-if="item.search_explanation.matched_evidence_fields.length">
        <strong>证据字段命中：</strong>{{ item.search_explanation.matched_evidence_fields.map(field => searchEvidenceFieldLabels[field]).join('、') }}
      </span>
      <span v-if="item.search_explanation.ai_summary_assisted">
        <strong>AI 总结低权重辅助召回</strong>
      </span>
    </p>

    <p
      v-if="item.tags?.includes('HOTSPOT_AWARDED') && item.relevance_reason"
      class="intelligence-card__search-match"
    >
      <strong>热点依据</strong>
      {{ item.relevance_reason }}
    </p>

    <section v-if="item.ai_judgment && !item.ai_summary_preview" class="intelligence-card__ai-judgment">
      <h4>AI 总结</h4>
      <p>{{ item.ai_judgment.why_worth_attention }}</p>
      <dl>
        <div v-if="item.ai_judgment.potential_industry_impacts?.length">
          <dt>可能的行业影响</dt>
          <dd>{{ item.ai_judgment.potential_industry_impacts?.join('；') }}</dd>
        </div>
        <div v-if="item.ai_judgment.potential_engineering_scenarios?.length">
          <dt>可能的工程应用场景</dt>
          <dd>{{ item.ai_judgment.potential_engineering_scenarios?.join('；') }}</dd>
        </div>
        <div v-if="item.ai_judgment.current_limitations?.length">
          <dt>当前局限</dt>
          <dd>{{ item.ai_judgment.current_limitations?.join('；') }}</dd>
        </div>
        <div v-if="item.ai_judgment.questions_to_verify?.length">
          <dt>待核实问题</dt>
          <dd>{{ item.ai_judgment.questions_to_verify?.join('；') }}</dd>
        </div>
      </dl>
    </section>

    <section
      v-if="(isUnverifiedAi || isAiFailure) && item.processing_failure_reasons?.length"
      class="intelligence-card__ai-failure"
      role="note"
    >
      <strong>{{ isUnverifiedAi ? '未通过 VERIFY' : '未生成可用 AI 判断' }}</strong>
      <ul>
        <li v-for="reason in item.processing_failure_reasons" :key="reason">
          {{ failureReasonLabel(reason) }}
        </li>
      </ul>
    </section>

    <p
      v-if="item.one_sentence_fact && item.review_status === 'APPROVED' && (item.ai_summary_preview || item.ai_assistance?.accepted_claims_only)"
      class="intelligence-card__ai-summary"
    >
      <strong>原文摘录：</strong>{{ item.one_sentence_fact }}
    </p>

    <section v-if="item.ai_summary_preview" class="intelligence-card__v2-ai-summary">
      <h4>AI 总结</h4>
      <p>{{ item.ai_summary_preview.body ?? item.ai_summary_preview.status_message }}</p>
    </section>

    <template v-if="!isWithdrawn && item.publication_revision_id && regulationSummary">
      <dl class="intelligence-card__facts">
        <div>
          <dt>文号</dt>
          <dd>{{ regulationSummary.document_number }}</dd>
        </div>
        <div>
          <dt>发布机关</dt>
          <dd>{{ regulationSummary.issuing_authority }}</dd>
        </div>
        <div>
          <dt>效力状态</dt>
          <dd>
            {{ regulationSummary.regulation_status === 'UNKNOWN' ? '效力状态待核验' : regulationSummary.regulation_status }}
          </dd>
        </div>
      </dl>
    </template>

    <template v-else-if="!isWithdrawn && paperSummary">
      <section class="intelligence-card__paper" data-testid="paper-summary">
        <dl class="intelligence-card__facts is-paper">
          <div>
            <dt>期刊</dt>
            <dd>{{ paperSummary.journal ?? '期刊待补充' }}</dd>
          </div>
          <div>
            <dt>年份 / 类型</dt>
            <dd>{{ paperSummary.year ?? '年份待补充' }} · {{ paperTypeLabels[paperSummary.paper_type] }}</dd>
          </div>
          <div>
            <dt>开放状态</dt>
            <dd>{{ paperAccessLabels[paperSummary.access_level] }}</dd>
          </div>
          <div>
            <dt>研究成熟度</dt>
            <dd>{{ maturityLabels[paperSummary.maturity_level] ?? paperSummary.maturity_level }}</dd>
          </div>
          <div v-if="paperSummary.doi" class="intelligence-card__doi">
            <dt>DOI</dt>
            <dd>{{ paperSummary.doi }}</dd>
          </div>
        </dl>
        <p class="intelligence-card__research-boundary">
          研究结果不代表已完成工程生产应用。
        </p>
      </section>
    </template>

    <template v-else-if="!isWithdrawn && productSummary">
      <section class="intelligence-card__product" data-testid="product-summary">
        <dl class="intelligence-card__facts is-product">
          <div><dt>厂商</dt><dd>{{ productSummary.vendor_name }}</dd></div>
          <div><dt>产品</dt><dd>{{ productSummary.product_name }}</dd></div>
          <div><dt>型号 / 版本</dt><dd>{{ [productSummary.model_no, productSummary.version].filter(Boolean).join(' / ') || '待补充' }}</dd></div>
          <div><dt>证据等级</dt><dd>{{ productEvidenceLabels[productSummary.evidence_level] ?? productSummary.evidence_level }}</dd></div>
          <div v-if="productSummary.kind === 'LOW_ALTITUDE_EQUIPMENT'">
            <dt>许可</dt><dd>{{ permitLabels[productSummary.permit_status] ?? productSummary.permit_status }}</dd>
          </div>
        </dl>
        <p class="intelligence-card__publisher-claim" data-testid="product-vendor-claims">
          厂商声明 {{ productSummary.promotional_claim_count }} 项
        </p>
        <p class="intelligence-card__verified-capabilities">
          独立验证 {{ productSummary.verified_capability_count }} 项
        </p>
        <p v-if="productSummary.kind === 'LOW_ALTITUDE_EQUIPMENT'" class="intelligence-card__product-boundary">
          产品发布不代表空域、适航、飞手和项目许可。
        </p>
      </section>
    </template>

    <template v-else-if="!isWithdrawn && digitalSummary">
      <section class="intelligence-card__digital" data-testid="digital-case-summary">
        <dl class="intelligence-card__facts is-digital-case">
          <div>
            <dt>成熟度</dt>
            <dd>{{ maturityLabels[digitalSummary.maturity_level] ?? digitalSummary.maturity_level }}</dd>
          </div>
          <div v-if="digitalSummary.application_scenarios.length">
            <dt>场景</dt>
            <dd>
              {{ digitalSummary.application_scenarios.map((value) => scenarioLabels[value] ?? value).join('、') }}
            </dd>
          </div>
          <div v-if="digitalSummary.deployment_scale">
            <dt>部署规模</dt>
            <dd>{{ digitalSummary.deployment_scale }}</dd>
          </div>
        </dl>
        <p v-if="digitalSummary.publisher_claim_label" class="intelligence-card__publisher-claim">
          {{ digitalSummary.publisher_claim_label }}
        </p>
        <p class="intelligence-card__relationship">
          <strong>与四川路桥的关系：</strong>{{ digitalSummary.srbg_relationship }}
        </p>
      </section>
    </template>

    <button
      v-if="item.scores?.relevance"
      type="button"
      class="intelligence-card__score"
      data-testid="score-summary"
      aria-haspopup="dialog"
      @click="scoreOpen = true"
    >
      相关度 {{ item.scores.relevance.score }}
    </button>

    <template v-else-if="!isWithdrawn && item.publication_revision_id && safetyCaseSummary">
      <dl class="intelligence-card__facts is-safety-case">
        <div v-if="safetyCaseSummary.engineering_type">
          <dt>工程类型</dt>
          <dd>{{ safetyEngineeringLabel(safetyCaseSummary.engineering_type) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.hazard_type">
          <dt>事故类型</dt>
          <dd>{{ safetyHazardLabel(safetyCaseSummary.hazard_type) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.occurred_at">
          <dt>发生时间</dt>
          <dd>{{ formatDate(safetyCaseSummary.occurred_at) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.region">
          <dt>地区</dt>
          <dd>{{ safetyCaseSummary.region }}</dd>
        </div>
        <div v-if="hasValue(safetyCaseSummary.deaths)">
          <dt>死亡人数</dt>
          <dd>{{ safetyCaseSummary.deaths }} 人</dd>
        </div>
        <div v-if="hasValue(safetyCaseSummary.injuries)">
          <dt>受伤人数</dt>
          <dd>{{ safetyCaseSummary.injuries }} 人</dd>
        </div>
        <div
          v-if="safetyCaseSummary.loss_amount_minor !== null
            && safetyCaseSummary.loss_amount_minor !== undefined
            && safetyCaseSummary.loss_currency"
        >
          <dt>直接经济损失</dt>
          <dd>
            {{ formatLoss(safetyCaseSummary.loss_amount_minor, safetyCaseSummary.loss_currency) }}
          </dd>
        </div>
        <div v-if="safetyCaseSummary.official_direct_causes?.length">
          <dt>正式原因</dt>
          <dd>{{ safetyCaseSummary.official_direct_causes.length }} 项已审核认定</dd>
        </div>
        <div v-if="safetyCaseSummary.responsibility_findings?.length">
          <dt>责任认定</dt>
          <dd>{{ safetyCaseSummary.responsibility_findings.length }} 项已审核认定</dd>
        </div>
      </dl>
    </template>

    <footer class="intelligence-card__footer">
      <a :href="item.original_url" target="_blank" rel="noreferrer">
        {{ originalLinkLabel }}
      </a>
      <a
        v-if="safetyCaseSummary?.event_id"
        :href="`/events/${safetyCaseSummary.event_id}`"
        data-testid="event-link"
      >
        查看事件时间线
      </a>
      <button
        v-if="item.publication_revision_id && item.evidence_status === 'VERIFIED'"
        type="button"
        data-testid="evidence-trigger"
        @click="emit('evidence', item.id)"
      >
        {{ isWithdrawn ? '查看历史证据' : '查看证据' }}（{{ item.evidence_count ?? 0 }}）
      </button>
      <button
        type="button"
        data-testid="save-item"
        :aria-pressed="saved"
        :disabled="saving || (isWithdrawn && !saved)"
        @click="toggleSaved"
      >
        {{ saving ? '处理中…' : saved ? '已收藏' : '收藏' }}
      </button>
      <span v-if="item.publication_revision_id && !isWithdrawn" class="intelligence-card__feedback">
        <span>这条情报有用吗？</span>
        <button
          type="button"
          data-testid="feedback-useful"
          :aria-pressed="feedback === 'USEFUL'"
          @click="recordFeedback('USEFUL')"
        >有用</button>
        <button
          type="button"
          data-testid="feedback-not-useful"
          :aria-pressed="feedback === 'NOT_USEFUL'"
          @click="recordFeedback('NOT_USEFUL')"
        >需改进</button>
      </span>
    </footer>
    <p v-if="saveProblem" class="intelligence-card__save-problem" role="alert">
      {{ saveProblem }}
    </p>
    <p v-if="feedbackProblem" class="intelligence-card__save-problem" role="alert">
      {{ feedbackProblem }}
    </p>
    <ScoreBreakdownDrawer
      v-if="item.scores"
      :open="scoreOpen"
      :scores="item.scores"
      @close="scoreOpen = false"
    />
  </article>
</template>

<style scoped>
.intelligence-card {
  display: grid;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.intelligence-card__meta,
.intelligence-card__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.intelligence-card__feedback {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  align-items: center;
}

.intelligence-card__type,
.intelligence-card__badge {
  padding: var(--spacing-1) var(--spacing-2);
  color: var(--color-ink-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-pill);
}

.intelligence-card__type {
  color: var(--color-safetyRegulation-700);
  background: var(--color-safetyRegulation-50);
}

.intelligence-card__type.is-safety-case {
  color: var(--color-safetyCase-700);
  background: var(--color-safetyCase-50);
}

.intelligence-card__type.is-digital-case {
  color: var(--color-digital-700);
  background: var(--color-digital-50);
}

.intelligence-card__type.is-paper {
  color: var(--color-digital-700);
  background: var(--color-digital-50);
}

.intelligence-card__badge.is-pending {
  color: var(--color-reviewPending-700);
  background: var(--color-reviewPending-50);
}

.intelligence-card__badge.is-reviewed {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
}

.intelligence-card__badge.is-ai {
  color: var(--color-brand-700);
  background: var(--color-brand-50);
}

.intelligence-card__ai-summary {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-ink-800);
  background: var(--color-brand-50);
  border-radius: var(--radius-sm);
}

.intelligence-card__search-match {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-brand-700);
  background: var(--color-brand-50);
  border-radius: var(--radius-sm);
}

.intelligence-card__save-problem {
  margin: 0;
  color: var(--color-conflict-700);
  font-size: var(--text-sm);
}

.intelligence-card__badge.is-document-state[data-document-state='UPDATED'] {
  color: var(--color-brand-700);
  background: var(--color-brand-50);
}

.intelligence-card__badge.is-document-state[data-document-state='RE_REVIEW_PENDING'] {
  color: var(--color-reviewPending-700);
  background: var(--color-reviewPending-50);
}

.intelligence-card__badge.is-document-state[data-document-state='WITHDRAWN'],
.intelligence-card__badge.is-document-state[data-document-state='SOURCE_UNAVAILABLE'] {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.intelligence-card__title {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
  line-height: var(--srbg-font-line-height-title);
}

.intelligence-card.is-unverified-ai {
  border-color: var(--color-reviewPending-500);
  background: var(--color-reviewPending-50);
}

.intelligence-card.is-ai-failure {
  border-style: dashed;
  border-color: var(--color-conflict-500);
}

.intelligence-card__ai-judgment,
.intelligence-card__ai-failure {
  display: grid;
  padding: var(--spacing-4);
  gap: var(--spacing-2);
  border-radius: var(--radius-md);
}

.intelligence-card__ai-judgment > p,
.intelligence-card__ai-summary,
.intelligence-card__v2-ai-summary > p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.intelligence-card__v2-ai-summary {
  background: var(--color-digital-50);
}

.intelligence-card__ai-judgment {
  background: var(--color-digital-50);
}

.intelligence-card__ai-failure {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.intelligence-card__ai-judgment h4,
.intelligence-card__ai-judgment p,
.intelligence-card__ai-judgment dl,
.intelligence-card__ai-failure ul {
  margin: 0;
}

.intelligence-card__title a {
  text-decoration: none;
}

.intelligence-card__title a:hover {
  text-decoration: underline;
}

.intelligence-card__source,
.intelligence-card__facts {
  display: grid;
  margin: 0;
  gap: var(--spacing-3);
}

.intelligence-card__source {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.intelligence-card__facts {
  padding: var(--spacing-4);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-md);
}

.intelligence-card__facts.is-safety-case {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  background: var(--color-safetyCase-50);
}

.intelligence-card__digital {
  display: grid;
  gap: var(--spacing-3);
}

.intelligence-card__paper {
  display: grid;
  gap: var(--spacing-3);
}

.intelligence-card__product {
  display: grid;
  gap: var(--spacing-3);
}

.intelligence-card__facts.is-product {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  background: var(--color-surfaceMuted);
}

.intelligence-card__verified-capabilities,
.intelligence-card__product-boundary {
  margin: 0;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
}

.intelligence-card__product-boundary {
  padding: var(--spacing-3);
  background: var(--color-reviewPending-50);
  border-radius: var(--radius-sm);
}

.intelligence-card__facts.is-paper {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  background: var(--color-digital-50);
}

.intelligence-card__doi dd {
  overflow-wrap: anywhere;
}

.intelligence-card__research-boundary {
  margin: 0;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
}

.intelligence-card__facts.is-digital-case {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  background: var(--color-digital-50);
}

.intelligence-card__publisher-claim,
.intelligence-card__relationship {
  margin: 0;
}

.intelligence-card__publisher-claim {
  justify-self: start;
  padding: var(--spacing-1) var(--spacing-2);
  color: var(--color-vendorClaim-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  background: var(--color-vendorClaim-50);
  border-radius: var(--radius-pill);
}

.intelligence-card__relationship {
  color: var(--color-ink-700);
}

.intelligence-card__relationship strong {
  color: var(--color-digital-700);
}

.intelligence-card__score {
  justify-self: start;
  padding: var(--spacing-3);
  color: var(--color-digital-700);
  font-weight: var(--font-weight-bold);
  background: var(--color-digital-50);
  border: 1px solid var(--color-digital-500);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.intelligence-card dl div {
  min-width: 0;
}

.intelligence-card dt {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.intelligence-card dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-800);
}

.intelligence-card__footer {
  justify-content: space-between;
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--color-border);
}

.intelligence-card__footer a,
.intelligence-card__footer button {
  color: var(--color-brand-700);
  font-weight: var(--font-weight-semibold);
}

.intelligence-card__footer button {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

@media (max-width: 40rem) {
  .intelligence-card {
    padding: var(--spacing-4);
  }

  .intelligence-card__source,
  .intelligence-card__facts.is-safety-case,
  .intelligence-card__facts.is-digital-case {
    grid-template-columns: 1fr;
  }

  .intelligence-card__facts.is-paper {
    grid-template-columns: 1fr;
  }

  .intelligence-card__facts.is-product {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 40.001rem) and (max-width: 63.999rem) {
  .intelligence-card__facts.is-safety-case {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
