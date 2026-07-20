<script setup lang="ts">
import type { EventAppendixV2 } from '@srbg/contracts'
import { computed, nextTick, ref } from 'vue'

type AppendixState = 'UNLOADED' | 'LOADING' | 'EMPTY' | 'SUCCESS' | 'ERROR' | 'RETRYING' | 'HEAVY'
type LoadedAppendix = EventAppendixV2 & {
  claims: NonNullable<EventAppendixV2['claims']>
  evidence: NonNullable<EventAppendixV2['evidence']>
  automatic_results: NonNullable<EventAppendixV2['automatic_results']>
  relationships: NonNullable<EventAppendixV2['relationships']>
  automatic_relationships: NonNullable<EventAppendixV2['automatic_relationships']>
  corrections: NonNullable<EventAppendixV2['corrections']>
  content_summary: NonNullable<EventAppendixV2['content_summary']> & {
    truncated_sections: NonNullable<NonNullable<EventAppendixV2['content_summary']>['truncated_sections']>
  }
}

const props = defineProps<{
  eventId: string
  endpoint?: string
}>()

const open = ref(false)
const state = ref<AppendixState>('UNLOADED')
const appendix = ref<LoadedAppendix | null>(null)
const toggleButton = ref<HTMLButtonElement | null>(null)
const errorMessage = ref('')
const endpoint = computed(() => props.endpoint ?? `/api/v2/events/${props.eventId}/appendix`)
const corrections = computed(() => [...(appendix.value?.corrections ?? [])]
  .sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at)))

const stageLabels: Readonly<Record<string, string>> = {
  INITIAL_REPORT: '初报',
  FOLLOW_UP_REPORT: '续报',
  FINAL_INVESTIGATION: '最终调查',
  ENFORCEMENT: '执法处罚',
  RECTIFICATION: '整改',
}
const relationLabels: Readonly<Record<string, string>> = {
  FOLLOW_UP: '后续', INVESTIGATES: '调查', PENALIZES: '处罚', RECTIFIES: '整改', CORRECTS: '更正',
}

function normalize(value: EventAppendixV2): LoadedAppendix {
  return {
    ...value,
    claims: value.claims ?? [],
    evidence: value.evidence ?? [],
    automatic_results: value.automatic_results ?? [],
    relationships: value.relationships ?? [],
    automatic_relationships: value.automatic_relationships ?? [],
    corrections: value.corrections ?? [],
    content_summary: {
      total_items: value.content_summary?.total_items ?? 0,
      heavy_content: value.content_summary?.heavy_content ?? false,
      truncated_sections: value.content_summary?.truncated_sections ?? [],
    },
  }
}

function isEmpty(value: LoadedAppendix): boolean {
  return value.claims.length === 0
    && value.evidence.length === 0
    && value.automatic_results.length === 0
    && value.relationships.length === 0
    && value.automatic_relationships.length === 0
    && value.corrections.length === 0
}

async function load(retrying = false): Promise<void> {
  state.value = retrying ? 'RETRYING' : 'LOADING'
  errorMessage.value = ''
  try {
    const value = normalize(await $fetch<EventAppendixV2>(endpoint.value, { retry: 0, timeout: 5_000 }))
    appendix.value = value
    state.value = isEmpty(value)
      ? 'EMPTY'
      : value.content_summary.heavy_content ? 'HEAVY' : 'SUCCESS'
  }
  catch {
    state.value = 'ERROR'
    errorMessage.value = '治理附录加载失败。主阅读内容不受影响，请稍后重试。'
  }
}

async function toggle(): Promise<void> {
  open.value = !open.value
  if (!open.value) {
    await nextTick()
    toggleButton.value?.focus()
    return
  }
  if (state.value === 'UNLOADED') await load()
}
</script>

<template>
  <section class="reader-appendix" aria-labelledby="reader-appendix-title">
    <h2 id="reader-appendix-title" class="reader-appendix__title">治理附录</h2>
    <button
      ref="toggleButton"
      data-testid="appendix-toggle"
      type="button"
      :aria-expanded="open"
      aria-controls="reader-appendix-panel"
      @click="toggle"
    >
      {{ open ? '收起' : '展开' }}证据、关系、更正与自动处理附录
    </button>

    <div
      v-if="open"
      id="reader-appendix-panel"
      class="reader-appendix__panel"
      :aria-busy="state === 'LOADING' || state === 'RETRYING'"
      aria-live="polite"
    >
      <p v-if="state === 'LOADING'">正在加载治理附录</p>
      <p v-else-if="state === 'RETRYING'">正在重试治理附录</p>
      <div v-else-if="state === 'ERROR'" class="reader-appendix__notice" role="alert">
        <p>{{ errorMessage }}</p>
        <button data-testid="appendix-retry" type="button" @click="load(true)">重试附录</button>
      </div>
      <div v-else-if="state === 'EMPTY'" class="reader-appendix__empty">
        <p>附录当前没有治理记录。</p>
        <p>Accepted claims：{{ appendix?.claims.length ?? 0 }}</p>
        <p>证据：{{ appendix?.evidence.length ?? 0 }}</p>
      </div>

      <template v-else-if="appendix">
        <aside v-if="state === 'HEAVY'" class="reader-appendix__notice" role="status">
          <strong>内容较多</strong>
          <span>共 {{ appendix.content_summary.total_items }} 条治理记录。</span>
          <span v-if="appendix.content_summary.truncated_sections.length">部分分组已按安全上限截断。</span>
        </aside>

        <section class="reader-appendix__group" aria-labelledby="appendix-evidence-title">
          <h3 id="appendix-evidence-title">AcceptedClaims 与证据</h3>
          <p>以下事实已通过证据定位；与模型输出保持独立。</p>
          <ul v-if="appendix.claims.length">
            <li v-for="claim in appendix.claims" :key="claim.id">
              <strong>{{ claim.label }}</strong>：{{ claim.value }}
              <span>（{{ claim.decision_status ?? '状态未提供' }}）</span>
            </li>
          </ul>
          <p v-else>没有 AcceptedClaim。</p>
          <ul v-if="appendix.evidence.length">
            <li v-for="evidence in appendix.evidence" :key="evidence.id">
              <blockquote>{{ evidence.excerpt }}</blockquote>
              <a :href="evidence.original_url" target="_blank" rel="noopener noreferrer">查看证据原文</a>
            </li>
          </ul>
          <p v-else>没有可投影证据。</p>
        </section>

        <section class="reader-appendix__group" aria-labelledby="appendix-automatic-title">
          <h3 id="appendix-automatic-title">自动处理结果（不是证据事实）</h3>
          <p>AI 与自动处理输出仅用于诊断，不能替代 AcceptedClaims。</p>
          <ul v-if="appendix.automatic_results.length">
            <li v-for="result in appendix.automatic_results" :key="result.signal_id">
              <strong>{{ result.result_type }}</strong>：{{ result.title }}
            </li>
          </ul>
          <p v-else>没有自动处理结果。</p>
        </section>

        <section class="reader-appendix__group" aria-labelledby="appendix-reviewed-relations-title">
          <h3 id="appendix-reviewed-relations-title">已审核关系</h3>
          <ul v-if="appendix.relationships.length">
            <li v-for="relation in appendix.relationships" :key="relation.id">
              <strong>{{ relationLabels[relation.relation_type] ?? relation.relation_type }}</strong>
              <span v-if="relation.from_stage || relation.to_stage">
                {{ stageLabels[relation.from_stage ?? ''] ?? '阶段未提供' }} →
                {{ stageLabels[relation.to_stage ?? ''] ?? '阶段未提供' }}
              </span>
            </li>
          </ul>
          <p v-else>没有已审核关系。</p>
        </section>

        <section class="reader-appendix__group" aria-labelledby="appendix-automatic-relations-title">
          <h3 id="appendix-automatic-relations-title">自动关系</h3>
          <p>自动关系为只读组合结果；纠正仍使用保留的 v1 关系边界。</p>
          <ul v-if="appendix.automatic_relationships.length">
            <li v-for="relation in appendix.automatic_relationships" :key="relation.id">
              <strong>{{ relation.kind }}</strong> · {{ relation.status }} · {{ relation.algorithm_version }}
            </li>
          </ul>
          <p v-else>没有自动关系。</p>
        </section>

        <section class="reader-appendix__group" aria-labelledby="appendix-corrections-title">
          <h3 id="appendix-corrections-title">结构化更正历史</h3>
          <ol v-if="corrections.length">
            <li v-for="correction in corrections" :key="correction.id">
              <time :datetime="correction.occurred_at">{{ new Date(correction.occurred_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</time>
              <strong>{{ correction.kind }}</strong>
              <span>{{ correction.description }}</span>
              <span>影响：{{ correction.affects.join('、') }}</span>
            </li>
          </ol>
          <p v-else>没有结构化更正。</p>
        </section>

        <footer class="reader-appendix__review">
          <p>阅读页不复制复核表单。</p>
          <a :href="appendix.review_context?.href ?? appendix.review_href">
            {{ appendix.review_context ? '打开对应复核案例' : '前往 Owner 复核列表' }}
          </a>
        </footer>
      </template>
    </div>
  </section>
</template>

<style scoped>
.reader-appendix { display: grid; gap: var(--spacing-3); }
.reader-appendix__title { margin: 0; color: var(--color-ink-900); font-size: var(--text-lg); }
.reader-appendix > button,
.reader-appendix__notice button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-4); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-ink-900); }
.reader-appendix__panel { display: grid; gap: var(--spacing-4); }
.reader-appendix__notice { display: flex; flex-wrap: wrap; gap: var(--spacing-2); padding: var(--spacing-3); background: var(--color-surfaceMuted); border-left: var(--spacing-1) solid var(--color-reviewPending-500); }
.reader-appendix__group { display: grid; gap: var(--spacing-2); padding-top: var(--spacing-4); border-top: 1px solid var(--color-border); }
.reader-appendix__group h3,
.reader-appendix__group p,
.reader-appendix__group blockquote,
.reader-appendix__empty p,
.reader-appendix__review p { margin: 0; }
.reader-appendix__empty { display: grid; gap: var(--spacing-1); }
.reader-appendix__group ul,
.reader-appendix__group ol { display: grid; gap: var(--spacing-2); margin: 0; padding-left: var(--spacing-5); }
.reader-appendix__group li { overflow-wrap: anywhere; }
.reader-appendix__group blockquote { margin-block: var(--spacing-1); color: var(--color-ink-800); }
.reader-appendix__review { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--spacing-3); padding-top: var(--spacing-4); border-top: 1px solid var(--color-border); }
</style>
