<script setup lang="ts">
import type { EventDetail, ProblemDetails } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import EventTimeline from '../../components/EventTimeline.vue'
import EventRelations from '../../components/EventRelations.vue'
import EventEvidenceDrawer from '../../components/EventEvidenceDrawer.vue'
import FactList from '../../components/FactList.vue'
import { safetyEngineeringLabel, safetyHazardLabel } from '../../utils/safety-case-labels'
import { createUuidV7 } from '../../utils/uuid-v7'

const route = useRoute()
const eventId = String(route.params.id)
const fallbackRequestId = createUuidV7()
const { data: detail, error, refresh, status } = await useFetch<EventDetail>(
  `/api/v1/events/${eventId}`,
  {
    key: `event:${eventId}`,
    retry: 0,
    server: false,
    timeout: 5_000,
  },
)
const content = computed(() => detail.value?.type_detail ?? null)
type TypeDetail = NonNullable<EventDetail['type_detail']>
type ProductTypeDetail = Extract<
  TypeDetail,
  { kind: 'AI_EQUIPMENT' | 'IOT_PRODUCT' | 'LOW_ALTITUDE_EQUIPMENT' | 'SOFTWARE_PRODUCT' }
>
const productContent = computed<ProductTypeDetail | null>(() => {
  const value = content.value
  if (!value) return null
  return isProductTypeDetail(value) ? value : null
})
const evidenceOpen = ref(false)
const selectedEvidenceIds = ref<string[]>([])
const selectedEvidence = computed(() => {
  const selected = new Set(selectedEvidenceIds.value)
  return (detail.value?.evidence ?? []).filter((entry) => selected.has(entry.evidence_id))
})
const selectedClaims = computed(() => {
  const selected = new Set(selectedEvidenceIds.value)
  return (detail.value?.claims ?? []).filter((claim) =>
    claim.evidence_ids.some((evidenceId) => selected.has(evidenceId)),
  )
})
const digitalPublishedClaims = computed(() => {
  if (content.value?.kind !== 'DIGITAL_CASE') return []
  return (detail.value?.claims ?? []).filter(
    claim => claim.field_name.toUpperCase() === 'CLAIMED_OUTCOME',
  )
})

const eventStatusMap = {
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
  NonNullable<EventDetail['incident_status']>,
  { label: string; tone: StatusBadgeTone }
>

const problem = computed<ProblemDetails | null>(() => {
  if (!error.value) return null
  const response = error.value.data
  if (
    response
    && typeof response === 'object'
    && 'title' in response
    && 'status' in response
    && 'request_id' in response
  ) {
    return response as ProblemDetails
  }

  const restricted = error.value.statusCode === 403
  return {
    detail: restricted
      ? '该事件包含受限安全信息，当前账号只能看到服务端允许的投影。'
      : '事件详情暂时无法加载，请稍后重试。',
    request_id: fallbackRequestId,
    status: restricted ? 403 : 503,
    title: restricted ? '事件访问受限' : '事件详情暂时不可用',
    type: 'about:blank',
  }
})

const statusPresentation = computed<{ label: string; tone: StatusBadgeTone } | null>(() => {
  const event = detail.value
  if (!event?.incident_status) return null
  if (event.incident_status === 'RECTIFICATION_FOLLOW_UP' && event.rectification_has_open_issues) {
    return { label: '整改评估完成但仍有问题', tone: 'conflict' }
  }
  return eventStatusMap[event.incident_status]
})

const shanghaiDateTime = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'long',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})

function formatDate(value: string | null | undefined): string {
  return value ? shanghaiDateTime.format(new Date(value)) : '待正式证据补充'
}

function scenarioTagLabel(tag: EventDetail['similar_scenario_tags'][number]): string {
  return {
    BRIDGE_APPROACH_TRANSITION: '桥头过渡段',
    EXTREME_WEATHER_EXPOSURE: '极端天气暴露',
    HIGHWAY_OPERATION_GEOLOGICAL_RISK: '运营高速公路地质风险',
    ROADBED_SLOPE_INSTABILITY: '路基边坡失稳',
    TEMPORARY_STRUCTURE_FAILURE: '临时结构失效',
    TUNNEL_GEOLOGICAL_RISK: '隧道地质风险',
  }[tag]
}

function preventionTagLabel(tag: EventDetail['prevention_measure_tags'][number]): string {
  return {
    CONSTRUCTION_QUALITY_CONTROL: '施工质量控制',
    DESIGN_REVIEW: '设计复核',
    EMERGENCY_PREPAREDNESS: '应急准备',
    HAZARD_IDENTIFICATION: '风险辨识',
    INSPECTION_AND_MAINTENANCE: '巡查与养护',
    MONITORING_AND_EARLY_WARNING: '监测与预警',
    RESPONSIBILITY_AND_OVERSIGHT: '责任与监督',
    TRAFFIC_OPERATION_RISK_CONTROL: '交通运营风险控制',
  }[tag]
}

function isProductTypeDetail(value: TypeDetail): value is ProductTypeDetail {
  switch (value.kind) {
    case 'AI_EQUIPMENT':
    case 'IOT_PRODUCT':
    case 'LOW_ALTITUDE_EQUIPMENT':
    case 'SOFTWARE_PRODUCT':
      return true
    default:
      return false
  }
}

function openEvidence(evidenceIds: string[]): void {
  selectedEvidenceIds.value = [...new Set(evidenceIds)]
  evidenceOpen.value = true
}

</script>

<template>
  <section class="event-detail-page">
    <PageHeader
      :title="detail?.title ?? '安全事件详情'"
      eyebrow="安全案例生命周期"
      description="初报、续报、正式调查、处罚与整改作为独立材料保留，不以近似去重覆盖。"
    >
      <template v-if="statusPresentation || detail?.unverified_facts.length" #status>
        <StatusBadge
          v-if="statusPresentation"
          :tone="statusPresentation.tone"
          :label="statusPresentation.label"
        />
        <StatusBadge
          v-if="detail?.unverified_facts.length"
          tone="conflict"
          label="冲突待核实"
        />
      </template>
    </PageHeader>

    <aside class="event-detail-page__notice">
      平台内容仅供内部信息参考，不替代正式制度、专业审查和现场安全决策。事故原因、责任、伤亡和损失仅展示有权机关证据且已人工复核的事实。
    </aside>

    <Skeleton
      v-if="status === 'idle' || status === 'pending'"
      :lines="8"
      label="正在加载安全事件"
    />
    <ProblemNotice
      v-else-if="problem"
      :problem="problem"
      retry-label="重新加载"
      @retry="refresh"
    />

    <template v-else-if="detail">
      <section v-if="content?.kind === 'DIGITAL_CASE'" class="event-detail-page__type-detail">
        <h2>发布方声称的成效</h2>
        <p>{{ content.publisher_claim_label ?? '未展示无 accepted claim 证据的发布方成效声明。' }}</p>
        <ul v-if="digitalPublishedClaims.length" class="event-detail-page__claim-list">
          <li v-for="claim in digitalPublishedClaims" :key="claim.claim_id">
            <span>{{ claim.value }}</span>
            <button
              v-if="claim.evidence_ids.length"
              class="event-detail-page__evidence-button"
              type="button"
              :aria-label="`查看成效证据（${claim.evidence_ids.length}）`"
              @click="openEvidence(claim.evidence_ids)"
            >
              查看成效证据
            </button>
          </li>
        </ul>
        <p v-else>暂无带原文定位的已接受发布方成效声明。</p>
        <h2>独立证据支持的成效</h2>
        <p>暂无可独立验证的量化成效。</p>
        <h2>复制条件</h2>
        <p>类型摘要不投影复制条件；具体结论必须来自 Event accepted claims 与证据。</p>
        <h2>限制与风险</h2>
        <p>来源属性和成熟度摘要不替代具体事实证据。</p>
        <p>仅供技术调研，不构成采购建议。</p>
      </section>

      <section v-if="content?.kind === 'JOURNAL_PAPER'" class="event-detail-page__type-detail">
        <h2>论文访问与证据边界</h2>
        <p>元数据可见</p>
        <p v-if="content.access_level === 'METADATA_ONLY'">当前发布投影仅含题录，未收录摘要。</p>
        <p v-if="content.access_level !== 'OPEN_FULLTEXT'">平台未保存全文，仅提供题录与原文链接。</p>
        <a :href="`/api/v1/events/${eventId}/citation?format=gb-t-7714`">复制 GB/T 7714</a>
        <a :href="`/api/v1/events/${eventId}/citation?format=ris`">导出 RIS</a>
        <a :href="`/api/v1/events/${eventId}/citation?format=bibtex`">导出 BibTeX</a>
        <h2>相似论文</h2>
      </section>

      <section v-if="productContent" class="event-detail-page__type-detail">
        <h2>产品能力</h2>
        <p>{{ productContent.verified_capability_count }} 项独立验证能力；{{ productContent.promotional_claim_count }} 项厂商声明。</p>
        <h2>工程证据</h2>
        <p>类型摘要不替代具体 claim 与 evidence。</p>
        <h2>许可与限制</h2>
        <p
          v-if="productContent.kind === 'LOW_ALTITUDE_EQUIPMENT'"
          class="item-detail-page__permit-boundary"
        >
          产品发布不代表空域、适航、飞手和项目许可。
        </p>
        <p>仅供技术调研，不构成采购建议。</p>
      </section>

      <section
        v-if="detail.incident_status === 'WITHDRAWN'"
        class="event-detail-page__withdrawn"
        role="status"
      >
        <StatusBadge tone="withdrawn" label="已撤回" />
        <p>当前事实结论已失效；历史阶段和关系仅为审计保留，请以更正材料为准。</p>
      </section>

      <dl class="event-detail-page__summary">
        <div>
          <dt>项目</dt>
          <dd>{{ detail.project_name ?? '待正式证据补充' }}</dd>
        </div>
        <div>
          <dt>发生时间</dt>
          <dd>{{ formatDate(detail.occurred_at) }}</dd>
        </div>
        <div>
          <dt>地区</dt>
          <dd>{{ detail.region ?? '待正式证据补充' }}</dd>
        </div>
        <div>
          <dt>工程类型</dt>
          <dd>{{ safetyEngineeringLabel(detail.engineering_type) ?? '待正式证据补充' }}</dd>
        </div>
        <div>
          <dt>事故类型</dt>
          <dd>{{ safetyHazardLabel(detail.hazard_type) ?? '待正式证据补充' }}</dd>
        </div>
      </dl>

      <div v-if="detail.incident_status !== 'WITHDRAWN'" class="event-detail-page__facts">
        <FactList
          title="已确认事实"
          variant="confirmed"
          :facts="detail.confirmed_facts"
          empty-description="正式调查证据和人工审核完成后才会进入本区。"
          @evidence="openEvidence"
        />
        <FactList
          title="待核实"
          variant="unverified"
          :facts="detail.unverified_facts"
          empty-description="当前没有向普通用户投影的未决关键事实。"
        />
      </div>

      <EventTimeline :items="detail.timeline.items" />

      <!-- SourceComparison is rendered from the complete Event detail projection. -->
      <section v-if="detail.source_comparison?.length" class="event-detail-page__type-detail">
        <h2>来源对比</h2>
        <ul>
          <li v-for="source in detail.source_comparison" :key="source.document_id">
            <a :href="source.original_url">{{ source.source_name }}</a>
            <span>{{ source.source_role ?? '待人工确认来源角色' }}</span>
          </li>
        </ul>
      </section>

      <EventRelations :items="detail.timeline.items" :relations="detail.relations" />

      <section class="event-detail-page__controlled-tags" aria-labelledby="scenario-tags-title">
        <div>
          <h2 id="scenario-tags-title">相似场景</h2>
          <ul v-if="detail.similar_scenario_tags.length" aria-label="受控相似场景标签">
            <li v-for="tag in detail.similar_scenario_tags" :key="tag">
              {{ scenarioTagLabel(tag) }}
            </li>
          </ul>
          <p v-else>暂无已审核相似场景标签。</p>
        </div>
        <div>
          <h2>防范措施主题</h2>
          <ul v-if="detail.prevention_measure_tags.length" aria-label="受控防范措施标签">
            <li v-for="tag in detail.prevention_measure_tags" :key="tag">
              {{ preventionTagLabel(tag) }}
            </li>
          </ul>
          <p v-else>暂无已审核防范措施标签。</p>
        </div>
        <p class="event-detail-page__tag-note">
          以上均为受控检索标签，只用于相似案例归类；不提供现场作业步骤，具体处置须经专业审查。
        </p>
      </section>
    </template>

    <EmptyState
      v-else-if="status === 'success'"
      title="事件详情为空"
      description="服务端未返回可见事件投影，请确认访问权限或稍后重试。"
      icon="EmptyPage"
    />

    <EventEvidenceDrawer
      :open="evidenceOpen"
      :claims="selectedClaims"
      :evidence="selectedEvidence"
      @close="evidenceOpen = false"
    />

  </section>
</template>

<style scoped>
.event-detail-page {
  display: grid;
  width: min(100%, var(--srbg-layout-reader-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.event-detail-page__notice,
.event-detail-page__withdrawn,
.event-detail-page__evidence-error {
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-sm);
}

.event-detail-page__type-detail {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.event-detail-page__claim-list {
  display: grid;
  margin: var(--spacing-3) 0 var(--spacing-5);
  padding: 0;
  list-style: none;
  gap: var(--spacing-2);
}

.event-detail-page__claim-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
  gap: var(--spacing-3);
}

.event-detail-page__evidence-button {
  min-height: var(--spacing-10);
  flex: none;
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-brand-700);
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.event-detail-page__notice {
  color: var(--color-ink-700);
  background: var(--color-safetyRegulation-50);
  border-left: 3px solid var(--color-safetyRegulation-500);
}

.event-detail-page__withdrawn {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid var(--color-conflict-500);
  gap: var(--spacing-3);
}

.event-detail-page__withdrawn p {
  margin: 0;
}

.event-detail-page__summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin: 0;
  padding: var(--spacing-5);
  background: var(--color-safetyCase-50);
  border: 1px solid var(--color-safetyCase-500);
  border-radius: var(--radius-lg);
  gap: var(--spacing-4);
}

.event-detail-page__summary dt {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.event-detail-page__summary dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-900);
  font-weight: var(--font-weight-semibold);
}

.event-detail-page__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: var(--spacing-4);
}

.event-detail-page__evidence-error {
  margin: 0;
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.event-detail-page__controlled-tags {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-5);
}

.event-detail-page__controlled-tags h2,
.event-detail-page__controlled-tags p {
  margin-top: 0;
}

.event-detail-page__controlled-tags ul {
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-2);
}

.event-detail-page__controlled-tags li {
  padding: var(--spacing-1) var(--spacing-2);
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-pill);
}

.event-detail-page__tag-note {
  grid-column: 1 / -1;
  margin-bottom: 0;
  padding-top: var(--spacing-3);
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  border-top: 1px solid var(--color-border);
}

@media (max-width: 63.999rem) {
  .event-detail-page__summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .event-detail-page__facts {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 47.999rem) {
  .event-detail-page__summary,
  .event-detail-page__controlled-tags {
    grid-template-columns: 1fr;
    padding: var(--spacing-4);
  }

  .event-detail-page__tag-note {
    grid-column: 1;
  }
}
</style>
