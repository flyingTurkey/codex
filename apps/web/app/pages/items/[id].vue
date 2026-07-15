<script setup lang="ts">
import type { ClaimView, EvidenceView, ItemDetail } from '@srbg/contracts'
import { PageHeader } from '@srbg/ui'
import { computed, ref } from 'vue'

import EvidenceDrawer from '../../components/EvidenceDrawer.vue'
import IntelligenceCard from '../../components/IntelligenceCard.vue'

const route = useRoute()
const itemId = String(route.params.id)
const { data: detail, status, error } = await useFetch<ItemDetail>(`/api/v1/items/${itemId}`, {
  server: false,
  retry: 0,
  timeout: 5_000,
})
const evidenceOpen = ref(false)
const selectedEvidenceIds = ref<string[] | null>(null)
const isDigitalCase = computed(() => detail.value?.item.content_type === 'DIGITAL_CASE')
const isPaper = computed(() => detail.value?.item.content_type === 'JOURNAL_PAPER')
const isProduct = computed(() => [
  'SOFTWARE_PRODUCT',
  'IOT_PRODUCT',
  'LOW_ALTITUDE_EQUIPMENT',
  'AI_EQUIPMENT',
].includes(detail.value?.item.content_type ?? ''))
const citationStatus = ref('')
const drawerEvidence = computed<EvidenceView[]>(() => {
  if (!selectedEvidenceIds.value) return detail.value?.evidence ?? []
  const ids = new Set(selectedEvidenceIds.value)
  return (detail.value?.evidence ?? []).filter((item) => ids.has(item.id))
})
const drawerClaims = computed<ClaimView[]>(() => {
  if (!selectedEvidenceIds.value) return detail.value?.claims ?? []
  const ids = new Set(selectedEvidenceIds.value)
  return (detail.value?.claims ?? []).filter((claim) => claim.evidence_ids.some((id) => ids.has(id)))
})

function openAllEvidence(): void {
  selectedEvidenceIds.value = null
  evidenceOpen.value = true
}

function openOutcomeEvidence(evidenceIds: string[]): void {
  selectedEvidenceIds.value = evidenceIds
  evidenceOpen.value = true
}

async function copyGbtCitation(): Promise<void> {
  citationStatus.value = ''
  try {
    const response = await fetch(`/api/v1/items/${itemId}/citation?format=gb-t-7714`)
    if (!response.ok) throw new Error('citation unavailable')
    const citation = await response.text()
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(citation)
    } else {
      const input = document.createElement('textarea')
      input.value = citation
      input.setAttribute('readonly', '')
      document.body.append(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    citationStatus.value = 'GB/T 7714 引用已复制'
  } catch {
    citationStatus.value = '引用复制失败，请使用导出文件'
  }
}

const actionLabels = {
  READ_ORIGINAL: '阅读原文',
  SAVE: '收藏',
  FOLLOW: '关注',
  TECHNICAL_RESEARCH: '技术调研',
} as const
</script>

<template>
  <section class="item-detail-page">
    <PageHeader
      :title="isProduct ? '技术产品详情' : isPaper ? '期刊论文详情' : isDigitalCase ? '数字化案例详情' : '安全情报详情'"
      :eyebrow="isProduct ? '统一型号、能力证据与许可边界' : isPaper ? '题录、研究解读与版权边界' : isDigitalCase ? '案例结构、归因与证据' : '字段与证据'"
      :description="isProduct
        ? '厂商声明与独立验证严格分列；型号版本保留历史，页面不形成采购结论。'
        : isPaper
        ? '元数据、摘要和全文权限分别展示；研究结论不代表工程生产应用。'
        : isDigitalCase
         ? '发布方成效与独立验证严格分列；相关性只表达与四川路桥业务的匹配程度。'
        : '待审核内容由服务端限制投影；发布后才显示审核通过的字段与段落证据。'"
    />

    <p v-if="status === 'pending'" role="status">正在加载详情…</p>
    <p v-else-if="error" role="alert">详情暂时不可用。</p>
    <template v-else-if="detail">
      <div v-if="detail.notice" class="item-detail-page__notice" role="status">
        {{ detail.notice.message }}
      </div>
      <IntelligenceCard :item="detail.item" :heading-level="2" @evidence="evidenceOpen = true" />

      <template v-if="detail.technology_product">
        <section class="item-detail-page__panel item-detail-page__product-capabilities">
          <div class="item-detail-page__product-heading">
            <div>
              <h2>产品能力</h2>
              <p>{{ detail.technology_product.vendor.name }} · {{ detail.technology_product.product.name }}</p>
              <p>型号/版本：{{ [detail.technology_product.model?.name, detail.technology_product.current_version].filter(Boolean).join(' / ') || '待补充' }}</p>
            </div>
            <div class="item-detail-page__product-placeholder" role="img" aria-label="厂商产品图片占位">
              <span aria-hidden="true">产品图片</span>
              <small>默认不下载厂商图片</small>
            </div>
          </div>
          <div class="item-detail-page__capability-groups">
            <div class="item-detail-page__vendor-claims">
              <h3>厂商声明</h3>
              <article v-for="capability in detail.technology_product.promotional_claims" :key="capability.claim_id">
                <strong>{{ capability.statement }}</strong>
                <span>归因：{{ capability.attribution }}</span>
                <button type="button" @click="openOutcomeEvidence(capability.evidence_ids)">查看声明证据</button>
              </article>
              <p v-if="!detail.technology_product.promotional_claims.length">暂无已接受的厂商声明。</p>
            </div>
            <div>
              <h3>已验证能力</h3>
              <article v-for="capability in detail.technology_product.verified_capabilities" :key="capability.claim_id">
                <strong>{{ capability.statement }}</strong>
                <span>独立证据：{{ capability.independent_evidence_ids?.length ?? 0 }} 条</span>
                <button type="button" @click="openOutcomeEvidence(capability.independent_evidence_ids ?? [])">查看独立证据</button>
              </article>
              <p v-if="!detail.technology_product.verified_capabilities.length">暂无独立证据支持的能力。</p>
            </div>
          </div>
        </section>

        <section class="item-detail-page__panel item-detail-page__product-evidence">
          <h2>工程证据</h2>
          <dl>
            <div><dt>证据等级</dt><dd>{{ detail.technology_product.evidence_level }}</dd></div>
            <div><dt>产品类型</dt><dd>{{ detail.technology_product.product_kind }}</dd></div>
            <div><dt>接口</dt><dd>{{ detail.technology_product.interfaces.join('、') || '未提供' }}</dd></div>
            <div><dt>部署方式</dt><dd>{{ detail.technology_product.deployment_modes.join('、') || '未提供' }}</dd></div>
            <div><dt>应用场景</dt><dd>{{ detail.technology_product.application_scenarios.join('、') || '未提供' }}</dd></div>
            <div><dt>历史版本</dt><dd>{{ detail.technology_product.version_history.join('、') || '暂无历史版本' }}</dd></div>
          </dl>
          <h3>已应用于数字化案例（APPLIED_IN）</h3>
          <ul v-if="detail.technology_product.engineering_cases.length">
            <li v-for="engineeringCase in detail.technology_product.engineering_cases" :key="engineeringCase.item_id">
              <a :href="`/items/${engineeringCase.item_id}`">{{ engineeringCase.title }}</a>
              <button type="button" @click="openOutcomeEvidence(engineeringCase.evidence_ids)">查看关系证据</button>
            </li>
          </ul>
          <p v-else>暂无已审核发布的工程应用关系。</p>
        </section>

        <section class="item-detail-page__panel item-detail-page__product-limitations">
          <h2>许可与限制</h2>
          <p><strong>许可状态：</strong>{{ detail.technology_product.permit_status }}</p>
          <ul><li v-for="limitation in detail.technology_product.limitations" :key="limitation">{{ limitation }}</li></ul>
          <p class="item-detail-page__procurement-boundary">
            {{ detail.technology_product.procurement_notice || '仅供技术调研，不构成采购建议' }}
          </p>
          <p v-if="detail.item.content_type === 'LOW_ALTITUDE_EQUIPMENT'" class="item-detail-page__permit-boundary">
            {{ detail.technology_product.low_altitude_notice || '产品发布不代表空域、适航、飞手和项目许可。' }}
          </p>
        </section>
      </template>

      <template v-if="detail.paper">
        <section class="item-detail-page__panel item-detail-page__paper-access">
          <h2>题录与访问权限</h2>
          <p><strong>元数据可见：</strong>题名、作者、机构、期刊、卷期、年份、DOI和关键词。</p>
          <dl>
            <div><dt>DOI</dt><dd>{{ detail.paper.doi ?? '未提供 DOI' }}</dd></div>
            <div><dt>期刊</dt><dd>{{ detail.paper.journal ?? '待补充' }}</dd></div>
            <div><dt>ISSN</dt><dd>{{ detail.paper.issns.join('、') || '待补充' }}</dd></div>
            <div><dt>卷期页</dt><dd>{{ [detail.paper.volume, detail.paper.issue, detail.paper.pages].filter(Boolean).join(' / ') || '待补充' }}</dd></div>
            <div><dt>作者</dt><dd>{{ detail.paper.authors.map((author) => author.name).join('、') || '待补充' }}</dd></div>
            <div><dt>机构</dt><dd>{{ [...new Set(detail.paper.authors.flatMap((author) => author.institutions))].join('、') || '待补充' }}</dd></div>
          </dl>
          <div class="item-detail-page__access-boundary">
            <p v-if="detail.paper.abstract_availability === 'AVAILABLE'">
              <strong>摘要可展示：</strong>{{ detail.paper.abstract }}
            </p>
            <p v-else-if="detail.paper.abstract_availability === 'LICENCE_UNCLEAR'">
              <strong>摘要：</strong>许可不明确，未收录摘要。
            </p>
            <p v-else><strong>摘要：</strong>来源未提供摘要。</p>
            <p v-if="detail.paper.access_level === 'OPEN_FULLTEXT'">
              <strong>全文：</strong>提供开放原文入口，平台未保存全文。
            </p>
            <p v-else><strong>全文：</strong>平台未保存全文，仅提供题录与原文链接。</p>
          </div>
        </section>

        <section class="item-detail-page__panel item-detail-page__paper-interpretation">
          <h2>研究解读</h2>
          <p class="item-detail-page__research-warning">研究结果不代表已完成工程生产应用。</p>
          <template v-if="detail.paper.research_interpretation">
            <dl>
              <div><dt>研究对象</dt><dd>{{ detail.paper.research_interpretation.research_object ?? '证据未说明' }}</dd></div>
              <div><dt>研究方法</dt><dd>{{ detail.paper.research_interpretation.method ?? '证据未说明' }}</dd></div>
            </dl>
            <h3>研究条件</h3>
            <ul><li v-for="value in detail.paper.research_interpretation.conditions" :key="value">{{ value }}</li></ul>
            <h3>结论</h3>
            <ul><li v-for="value in detail.paper.research_interpretation.conclusions" :key="value">{{ value }}</li></ul>
            <h3>局限</h3>
            <ul><li v-for="value in detail.paper.research_interpretation.limitations" :key="value">{{ value }}</li></ul>
          </template>
          <p v-else>暂无已接受且具有证据引用的研究解读。</p>
        </section>

        <section class="item-detail-page__panel item-detail-page__citation">
          <h2>引用与题录导出</h2>
          <button type="button" @click="copyGbtCitation">复制 GB/T 7714</button>
          <a :href="`/api/v1/items/${itemId}/citation?format=ris`">导出 RIS</a>
          <a :href="`/api/v1/items/${itemId}/citation?format=bibtex`">导出 BibTeX</a>
          <a :href="detail.paper.open_fulltext_url ?? detail.item.original_url" target="_blank" rel="noreferrer">
            查看原文入口
          </a>
          <p aria-live="polite">{{ citationStatus }}</p>
        </section>

        <section class="item-detail-page__panel item-detail-page__similar-papers">
          <h2>相似论文</h2>
          <ul v-if="detail.paper.similar_papers.length">
            <li v-for="paper in detail.paper.similar_papers" :key="paper.item_id">
              <a :href="`/items/${paper.item_id}`">{{ paper.title }}</a>
              <span>{{ paper.match_reasons.join('；') }}</span>
            </li>
          </ul>
          <p v-else>暂无当前用户可见的相似论文。</p>
        </section>
      </template>

      <template v-if="detail.digital_case">
        <section class="item-detail-page__panel item-detail-page__taxonomy">
          <h2>案例结构</h2>
          <dl>
            <div><dt>工程专业</dt><dd>{{ detail.digital_case.engineering_domains.join('、') || '待分类' }}</dd></div>
            <div><dt>生命周期</dt><dd>{{ detail.digital_case.lifecycle_stages.join('、') || '待分类' }}</dd></div>
            <div><dt>技术标签</dt><dd>{{ detail.digital_case.technology_tags.join('、') || '待分类' }}</dd></div>
            <div><dt>应用场景</dt><dd>{{ detail.digital_case.application_scenarios.join('、') || '待分类' }}</dd></div>
          </dl>
          <h3>企业、技术与项目关系</h3>
          <ul>
            <li v-for="entity in detail.digital_case.entities" :key="entity.id">
              {{ entity.name }} · {{ entity.relation_type }}
            </li>
          </ul>
        </section>

        <section class="item-detail-page__panel item-detail-page__outcomes">
          <div>
            <h2>发布方声称的成效</h2>
            <p>以下结果保留发布方归因，不代表平台独立核验。</p>
            <article v-for="outcome in detail.digital_case.claimed_outcomes" :key="outcome.id">
              <strong>{{ outcome.statement }}</strong>
              <span>归因：{{ outcome.attribution }}</span>
              <button type="button" @click="openOutcomeEvidence(outcome.evidence_ids)">
                查看成效证据（{{ outcome.evidence_ids.length }}）
              </button>
            </article>
            <p v-if="!detail.digital_case.claimed_outcomes.length">暂无发布方量化成效。</p>
          </div>
          <div>
            <h2>独立证据支持的成效</h2>
            <p>仅收录存在独立证据来源的结果。</p>
            <article v-for="outcome in detail.digital_case.verified_outcomes" :key="outcome.id">
              <strong>{{ outcome.statement }}</strong>
              <span>归因：{{ outcome.attribution }}</span>
              <button type="button" @click="openOutcomeEvidence(outcome.independent_evidence_ids ?? [])">
                查看独立证据（{{ outcome.independent_evidence_ids?.length ?? 0 }}）
              </button>
            </article>
            <p v-if="!detail.digital_case.verified_outcomes.length">暂无可独立验证的量化成效。</p>
          </div>
        </section>

        <section class="item-detail-page__panel item-detail-page__replication">
          <div><h2>适用性</h2><ul><li v-for="item in detail.digital_case.applicability" :key="item">{{ item }}</li></ul></div>
          <div><h2>复制条件</h2><ul><li v-for="item in detail.digital_case.replication_conditions" :key="item">{{ item }}</li></ul></div>
          <div><h2>限制与风险</h2><ul><li v-for="item in [...detail.digital_case.limitations, ...detail.digital_case.risks]" :key="item">{{ item }}</li></ul></div>
        </section>

        <section class="item-detail-page__panel item-detail-page__actions">
          <h2>可执行动作</h2>
          <ul><li v-for="action in detail.digital_case.recommended_actions" :key="action">{{ actionLabels[action] }}</li></ul>
          <p>动作仅用于情报跟进，不形成采购结论。</p>
        </section>
      </template>

      <section v-if="detail.claims?.length" class="item-detail-page__claims item-detail-page__panel">
        <h2>已接受字段</h2>
        <dl>
          <div v-for="claim in detail.claims" :key="claim.id">
            <dt>{{ claim.label }}</dt>
            <dd>{{ claim.value }}</dd>
          </div>
        </dl>
        <button type="button" @click="openAllEvidence">
          查看 {{ detail.evidence?.length ?? 0 }} 条字段证据
        </button>
      </section>
    </template>

    <EvidenceDrawer
      :open="evidenceOpen"
      :item-id="itemId"
      :claims="drawerClaims"
      :evidence="drawerEvidence"
      @close="evidenceOpen = false"
    />
  </section>
</template>

<style scoped>
.item-detail-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.item-detail-page__notice {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
  border: 1px solid var(--color-reviewPending-300);
  border-radius: var(--radius-sm);
}

.item-detail-page__panel {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.item-detail-page__panel h2,
.item-detail-page__panel h3,
.item-detail-page__panel p {
  margin-top: 0;
}

.item-detail-page__product-heading,
.item-detail-page__capability-groups,
.item-detail-page__product-evidence dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-4);
}

.item-detail-page__product-placeholder {
  display: grid;
  min-height: 8rem;
  place-content: center;
  color: var(--color-ink-500);
  text-align: center;
  background: var(--color-surfaceMuted);
  border: 1px dashed var(--color-borderStrong);
  border-radius: var(--radius-md);
}

.item-detail-page__capability-groups article {
  display: grid;
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
  gap: var(--spacing-2);
}

.item-detail-page__vendor-claims article {
  color: var(--color-vendorClaim-700);
  background: var(--color-vendorClaim-50);
}

.item-detail-page__procurement-boundary,
.item-detail-page__permit-boundary {
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
  border-radius: var(--radius-sm);
}

.item-detail-page__taxonomy dl,
.item-detail-page__outcomes,
.item-detail-page__replication {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-4);
}

.item-detail-page__outcomes article {
  display: grid;
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-left: var(--spacing-1) solid var(--color-brand-500);
  border-radius: var(--radius-sm);
  gap: var(--spacing-2);
}

.item-detail-page__outcomes button {
  justify-self: start;
}

.item-detail-page__actions p {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

.item-detail-page__claims h2 {
  margin-top: 0;
}

.item-detail-page__claims dl {
  display: grid;
  gap: var(--spacing-3);
}

.item-detail-page__claims dt {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.item-detail-page__claims dd {
  margin: var(--spacing-1) 0 0;
}

.item-detail-page__claims button {
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-surface);
  background: var(--color-brand-700);
  border: 0;
  border-radius: var(--radius-sm);
}

.item-detail-page__paper-access dl,
.item-detail-page__paper-interpretation dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-3);
}

.item-detail-page__access-boundary,
.item-detail-page__research-warning {
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
}

.item-detail-page__citation {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
}

.item-detail-page__citation h2,
.item-detail-page__citation p {
  flex-basis: 100%;
}

.item-detail-page__similar-papers li {
  display: grid;
  gap: var(--spacing-1);
}

.item-detail-page__similar-papers span {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

@media (max-width: 47.999rem) {
  .item-detail-page__taxonomy dl,
  .item-detail-page__outcomes,
  .item-detail-page__replication {
    grid-template-columns: 1fr;
  }

  .item-detail-page__paper-access dl,
  .item-detail-page__paper-interpretation dl {
    grid-template-columns: 1fr;
  }

  .item-detail-page__product-heading,
  .item-detail-page__capability-groups,
  .item-detail-page__product-evidence dl {
    grid-template-columns: 1fr;
  }
}
</style>
