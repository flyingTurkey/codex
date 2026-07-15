<script setup lang="ts">
import type { EventDetail, ItemDetail, ProblemDetails, SourceComparison as SourceComparisonContract } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import EventTimeline from '../../components/EventTimeline.vue'
import EventRelations from '../../components/EventRelations.vue'
import EvidenceDrawer from '../../components/EvidenceDrawer.vue'
import FactList from '../../components/FactList.vue'
import SourceComparison from '../../components/SourceComparison.vue'
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
const { data: sourceComparison } = await useFetch<SourceComparisonContract>(
  `/api/v1/events/${eventId}/source-comparison`,
  { key: `event-sources:${eventId}`, retry: 0, server: false, timeout: 5_000 },
)

const evidenceDetail = ref<ItemDetail | null>(null)
const evidenceOpen = ref(false)
const evidenceLoading = ref(false)
const evidenceError = ref(false)

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

async function openEvidence(itemId: string): Promise<void> {
  evidenceLoading.value = true
  evidenceError.value = false
  try {
    evidenceDetail.value = await $fetch<ItemDetail>(`/api/v1/items/${itemId}`, {
      retry: 0,
      timeout: 5_000,
    })
    evidenceOpen.value = true
  } catch {
    evidenceError.value = true
  } finally {
    evidenceLoading.value = false
  }
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

      <p v-if="evidenceLoading" role="status">正在加载字段证据…</p>
      <p v-if="evidenceError" class="event-detail-page__evidence-error" role="alert">
        字段证据暂时无法加载，请稍后重试。
      </p>

      <EventTimeline :items="detail.timeline.items" />

      <SourceComparison v-if="sourceComparison" :comparison="sourceComparison" />

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

    <EvidenceDrawer
      :open="evidenceOpen"
      :item-id="evidenceDetail?.item.id"
      :claims="evidenceDetail?.claims ?? []"
      :evidence="evidenceDetail?.evidence ?? []"
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
