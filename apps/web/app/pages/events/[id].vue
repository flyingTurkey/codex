<script setup lang="ts">
import type { EventFullProjectionV2, EventMetadataProjectionV2, ProblemDetails } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'

type EventProjection = EventFullProjectionV2 | EventMetadataProjectionV2
type SummaryStatus = EventFullProjectionV2['ai_summary']['status']

const primaryTypeLabels: Record<EventProjection['primary_type'], string> = {
  DIGITAL_TRANSFORMATION: '数字化转型',
  SAFETY_INTELLIGENCE: '安全情报',
  INDUSTRY_UPDATE: '行业更新',
}
const facetLabels: Readonly<Record<string, string>> = {
  HIGHWAY: '公路', RAILWAY: '铁路', BRIDGE: '桥梁', TUNNEL: '隧道', BUILDING: '房屋建筑',
  MINING: '矿山', MUNICIPAL: '市政', WATER_CONSERVANCY: '水利', PORT_WATERWAY: '港航',
  AIRPORT: '机场', ENERGY: '能源工程', TUNNEL_GAS_MONITORING: '隧道瓦斯监测',
  CONSTRUCTION_MACHINERY: '工程施工机械',
}
const claimBasisLabels: Readonly<Record<EventFullProjectionV2['claim_basis'][number], string>> = {
  MANUFACTURER_CLAIM: '厂商声明',
  RESEARCH_CONCLUSION: '研究结论',
  PROJECT_FIRST_PARTY_RECORD: '项目第一方记录',
  INDEPENDENT_VERIFICATION: '独立验证',
  AUTHORITY_FINDING: '权威认定',
}
const summaryStateLabels: Record<SummaryStatus, string> = {
  NOT_GENERATED: '尚未生成',
  PROCESSING: '处理中',
  TEMPORARILY_UNAVAILABLE: '暂时不可用',
  SCHEMA_REJECTED: '结构校验拒绝',
  INSUFFICIENT_EVIDENCE: '证据不足',
  SUCCEEDED: '已生成',
  STALE: '已失效',
}

const route = useRoute()
const eventId = String(route.params.id)
const result = await useFetch<EventProjection>(`/api/v2/events/${eventId}`, {
  key: `event-v2:${eventId}`, server: false, retry: 0, timeout: 5_000,
})
const detail = computed(() => result.data.value)
const full = computed(() => detail.value?.projection_kind === 'FULL' ? detail.value : null)
const problem = computed(() => result.error.value?.data as ProblemDetails ?? null)
const shanghai = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short', timeZone: 'Asia/Shanghai' })

function formatDate(value: string | null | undefined): string {
  return value ? shanghai.format(new Date(value)) : '原文未提供'
}

function labelFacet(value: string): string {
  return facetLabels[value] ?? value
}

function summaryTone(status: SummaryStatus): StatusBadgeTone {
  if (status === 'SUCCEEDED') return 'info'
  if (status === 'STALE' || status === 'SCHEMA_REJECTED') return 'conflict'
  if (status === 'TEMPORARILY_UNAVAILABLE') return 'degraded'
  return 'pending'
}

</script>

<template>
  <section class="reader-page">
    <PageHeader :title="detail?.title ?? '情报阅读'" eyebrow="土木工程情报阅读页">
      <template v-if="detail" #status>
        <StatusBadge tone="info" :label="primaryTypeLabels[detail.primary_type]" />
        <span>{{ formatDate(detail.source_published_at) }}</span>
      </template>
    </PageHeader>
    <Skeleton v-if="result.status.value === 'idle' || result.status.value === 'pending'" :lines="8" label="正在加载情报" />
    <ProblemNotice v-else-if="problem" :problem="problem" @retry="result.refresh" />
    <template v-else-if="detail">
      <aside v-if="full?.correction_alert" class="reader-page__correction" role="alert">
        <strong>更正或撤回提醒</strong>
        <span>{{ full.correction_alert }}</span>
      </aside>

      <div v-if="detail.projection_kind === 'R3_METADATA'" class="reader-page__r3">
        <aside class="reader-context" data-reader-area="context" aria-labelledby="reader-context-title">
          <h2 id="reader-context-title">来源上下文</h2>
          <dl>
            <div><dt>来源</dt><dd>{{ detail.source_name }}</dd></div>
            <div><dt>来源属性</dt><dd><StatusBadge :tone="detail.official_source ? 'verified' : 'vendor'" :label="detail.official_source ? '官方一手来源' : '非官方来源'" /></dd></div>
            <div><dt>主类型</dt><dd>{{ primaryTypeLabels[detail.primary_type] }}</dd></div>
            <div><dt>原文发布时间</dt><dd>{{ formatDate(detail.source_published_at) }}</dd></div>
            <div><dt>首次发现时间</dt><dd>{{ formatDate(detail.first_discovered_at) }}</dd></div>
          </dl>
        </aside>
        <aside class="reader-page__pending">
          <StatusBadge tone="pending" label="待 Owner 审核" />
          <p>当前为 R3 元数据投影，正文、证据、媒体和 AI 内容尚未向普通阅读面开放。</p>
        </aside>
        <ReaderActions :original-url="detail.original_url" aria-label="查看原文与材料" />
      </div>

      <div v-else-if="full" class="reader-layout">
        <aside class="reader-context" data-reader-area="context" aria-labelledby="reader-context-title">
          <h2 id="reader-context-title">来源上下文</h2>
          <dl>
            <div><dt>来源</dt><dd>{{ full.source.name }}</dd></div>
            <div>
              <dt>来源属性</dt>
              <dd><StatusBadge :tone="full.source.official ? 'verified' : 'vendor'" :label="full.source.official ? '官方一手来源' : '非官方来源'" /></dd>
            </div>
            <div>
              <dt>人工复核</dt>
              <dd><StatusBadge :tone="full.human_reviewed ? 'verified' : 'pending'" :label="full.human_reviewed ? '已人工复核' : '机器整理／未人工复核'" /></dd>
            </div>
            <div><dt>原文发布时间</dt><dd>{{ formatDate(full.source_published_at) }}</dd></div>
            <div><dt>首次发现时间</dt><dd>{{ formatDate(full.first_discovered_at) }}</dd></div>
            <div><dt>主类型</dt><dd>{{ primaryTypeLabels[full.primary_type] }}</dd></div>
            <div>
              <dt>工程对象与 facets</dt>
              <dd class="reader-context__tags">
                <span v-for="facet in [...full.facets.engineering_objects, ...(full.facets.specialties ?? []), ...(full.facets.equipment_domains ?? []), ...(full.facets.cross_type_tags ?? [])]" :key="facet">{{ labelFacet(facet) }}</span>
              </dd>
            </div>
            <div>
              <dt>ClaimBasis</dt>
              <dd class="reader-context__tags"><span v-for="basis in full.claim_basis" :key="basis">{{ claimBasisLabels[basis] }}</span></dd>
            </div>
            <div v-if="full.hotspot">
              <dt>热点理由</dt>
              <dd>
                <p>{{ full.hotspot.independent_source_count }} 个独立来源</p>
                <ul><li v-for="reason in full.hotspot.reasons" :key="reason">{{ reason }}</li></ul>
              </dd>
            </div>
          </dl>
        </aside>

        <article class="reader-page__section reader-section reader-section--evidence" data-reader-area="source-excerpt">
          <header><p>来源证据</p><h2>原文摘录</h2></header>
          <blockquote>{{ full.source_excerpt.text }}</blockquote>
          <p class="reader-section__evidence-note">连续原文摘录 · 已绑定 {{ full.source_excerpt.claim_ids.length }} 项 AcceptedClaim</p>
        </article>

        <article class="reader-page__section reader-section reader-section--ai" data-reader-area="ai-summary" :data-summary-state="full.ai_summary.status">
          <header>
            <div><p>模型解读，不是证据</p><h2>AI 总结</h2></div>
            <StatusBadge :tone="summaryTone(full.ai_summary.status)" :label="summaryStateLabels[full.ai_summary.status]" />
          </header>
          <p class="reader-section__status-message">{{ full.ai_summary.status_message }}</p>
          <div v-if="full.ai_summary.status === 'SUCCEEDED' && full.ai_summary.paragraphs?.length" class="reader-summary">
            <section v-for="paragraph in full.ai_summary.paragraphs" :key="`${paragraph.section}:${paragraph.text}`" :class="{ 'reader-summary__judgment': paragraph.kind === 'JUDGMENT' }">
              <p class="reader-summary__kind">{{ paragraph.kind === 'JUDGMENT' ? 'AI 判断' : '基于已接受事实' }}</p>
              <p>{{ paragraph.text }}</p>
              <ul v-if="paragraph.kind === 'FACT'" class="reader-summary__claims">
                <li v-for="claim in paragraph.claim_ids" :key="claim"><code>AcceptedClaim：{{ claim }}</code></li>
              </ul>
            </section>
          </div>
          <p v-else-if="full.ai_summary.status === 'SUCCEEDED' && full.ai_summary.body" class="reader-page__summary">{{ full.ai_summary.body }}</p>
        </article>

        <section class="reader-page__section reader-section reader-section--materials" data-reader-area="materials">
          <header><p>经投影许可的材料</p><h2>媒体与材料</h2></header>
          <div v-if="full.media?.some(item => item.preview_url)" class="reader-media">
            <figure v-for="media in full.media.filter(item => item.preview_url)" :key="media.media_id">
              <img :src="media.preview_url ?? undefined" :alt="media.name">
              <figcaption>{{ media.name }}</figcaption>
            </figure>
          </div>
          <p v-else>当前没有可安全预览的许可媒体；可用材料动作见“阅读与材料”。</p>
        </section>

        <ReaderActions :original-url="full.original_url" :attachments="full.attachments" aria-label="查看原文与材料" />

        <section
          id="reader-appendix"
          class="reader-page__appendix"
          data-reader-area="appendix"
          aria-label="Accepted claims、证据、关系、更正与自动处理附录"
        >
          <ReaderAppendix :event-id="eventId" :endpoint="`/api/v2/events/${eventId}/appendix`" />
        </section>
      </div>
    </template>
    <EmptyState v-else title="情报不可见" description="该内容未通过普通阅读投影门禁。" />
  </section>
</template>

<style scoped>
.reader-page {
  display: grid;
  width: min(100%, var(--srbg-layout-reader-max));
  min-width: 0;
  margin-inline: auto;
  gap: var(--spacing-5);
}

.reader-context dd,
.reader-section,
.reader-page__pending,
.reader-page__appendix {
  overflow-wrap: anywhere;
}

.reader-page__correction {
  display: grid;
  gap: var(--spacing-1);
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
}

.reader-layout {
  display: grid;
  min-width: 0;
  align-items: start;
  grid-template-columns: minmax(0, var(--srbg-layout-detail-main)) minmax(16rem, 1fr);
  grid-template-areas:
    'excerpt context'
    'summary actions'
    'materials actions'
    'appendix appendix';
  gap: var(--spacing-5);
}

.reader-context,
.reader-section,
.reader-page__pending,
.reader-page__appendix {
  min-width: 0;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.reader-context {
  grid-area: context;
  position: sticky;
  top: calc(var(--srbg-layout-header) + var(--spacing-4));
  overflow: visible;
}

.reader-context h2,
.reader-context dl,
.reader-context dd,
.reader-context p,
.reader-context ul,
.reader-section h2,
.reader-section header p,
.reader-section blockquote,
.reader-page__pending p {
  margin: 0;
}

.reader-context dl {
  display: grid;
  gap: var(--spacing-4);
  margin-top: var(--spacing-4);
}

.reader-context dl > div {
  display: grid;
  gap: var(--spacing-1);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--color-border);
}

.reader-context dl > div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.reader-context dt,
.reader-section header > p,
.reader-section header div > p,
.reader-summary__kind,
.reader-section__evidence-note {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  line-height: var(--srbg-font-line-height-metadata);
}

.reader-context__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.reader-context__tags span {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-pill);
}

.reader-section--evidence { grid-area: excerpt; }
.reader-section--ai { grid-area: summary; background: var(--color-surfaceMuted); }
.reader-section--materials { grid-area: materials; }
.reader-page__appendix { grid-area: appendix; }

.reader-section--evidence {
  border-left: var(--spacing-1) solid var(--color-brand-600);
  box-shadow: var(--shadow-hover);
}

.reader-section header {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.reader-section h2 {
  color: var(--color-ink-900);
  font-size: var(--text-xl);
}

.reader-section blockquote {
  color: var(--color-ink-900);
  font-size: var(--text-md);
  line-height: var(--srbg-font-line-height-relaxed);
}

.reader-section__evidence-note {
  margin: var(--spacing-4) 0 0;
}

.reader-section__status-message {
  color: var(--color-ink-600);
}

.reader-summary {
  display: grid;
  gap: var(--spacing-4);
  margin-top: var(--spacing-4);
}

.reader-summary > section {
  padding: var(--spacing-4);
  background: var(--color-surface);
  border-left: 2px solid var(--color-digital-500);
  border-radius: var(--radius-sm);
}

.reader-summary__judgment {
  border-left-color: var(--color-reviewPending-500) !important;
}

.reader-summary__kind,
.reader-summary > section > p {
  margin-top: 0;
}

.reader-summary__claims {
  display: grid;
  gap: var(--spacing-1);
  padding-left: var(--spacing-5);
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.reader-page__summary {
  white-space: pre-line;
  line-height: var(--srbg-font-line-height-relaxed);
}

.reader-media {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));
  gap: var(--spacing-4);
}

.reader-media figure { margin: 0; }
.reader-media img { display: block; width: 100%; height: auto; border-radius: var(--radius-md); }
.reader-media figcaption { margin-top: var(--spacing-2); color: var(--color-ink-600); font-size: var(--text-sm); }

.reader-page__appendix button {
  min-height: var(--spacing-10);
}

.reader-page__r3 {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 22rem);
  gap: var(--spacing-5);
}

.reader-page__r3 .reader-context { grid-row: span 2; }
.reader-page__pending { display: grid; gap: var(--spacing-3); }

@media (max-width: 63.999rem) {
  .reader-layout {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      'context'
      'excerpt'
      'summary'
      'materials'
      'actions'
      'appendix';
  }

  .reader-context {
    position: static;
  }

  .reader-page__r3 {
    grid-template-columns: minmax(0, 1fr);
  }

  .reader-page__r3 .reader-context { grid-row: auto; }
}

@media (max-width: 47.999rem) {
  .reader-context,
  .reader-section,
  .reader-page__pending,
  .reader-page__appendix {
    padding: var(--spacing-4);
  }

  .reader-section header {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .reader-page *,
  .reader-page *::before,
  .reader-page *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
</style>
