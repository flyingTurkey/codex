<script setup lang="ts">
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'
import { computed, reactive, ref } from 'vue'

type GoldKind = 'DOCUMENT' | 'PAIR' | 'EVENT' | 'CLAIM_EVIDENCE' | 'SEARCH_QUESTION'

interface GoldTask {
  id: string
  sample_kind: GoldKind
  sample_ref: string
  source_code: string
  domain: 'DIGITAL' | 'SAFETY'
  production_decision_id: string
  critical_safety: boolean
  secondary_review_required: boolean
  status: 'ASSIGNED' | 'SUBMITTED' | 'DISAGREEMENT' | 'ARBITRATED' | 'FROZEN'
  assigned_at: string
}

interface ArbitrationPacket {
  task: GoldTask
  options: Array<{
    annotation_id: string
    decision_code: string
    label_value: string | null
    evidence_ids: string[]
    related_sample_refs: string[]
  }>
}

const message = ref<string | null>(null)
const busyTaskId = ref<string | null>(null)
const annotationDecision = ref<Record<string, string>>({})
const annotationLabel = ref<Record<string, string>>({})
const annotationEvidence = ref<Record<string, string>>({})
const arbitrationSelection = ref<Record<string, string>>({})
const arbitrationReason = ref<Record<string, string>>({})
const arbitrationPackets = ref<Record<string, ArbitrationPacket>>({})
const releaseReason = ref('冻结经双标和仲裁的第一阶段人工金标')

const creation = reactive({
  sampleKind: 'DOCUMENT' as GoldKind,
  sampleRef: '',
  sourceCode: '',
  domain: 'DIGITAL' as 'DIGITAL' | 'SAFETY',
  productionDecisionId: '',
  annotatorA: '',
  annotatorB: '',
  criticalSafety: false,
  reason: '分配经批准的第17轮业务金标任务',
})

const {
  data: tasks,
  error,
  refresh,
  status,
} = await useFetch<GoldTask[]>('/api/v1/admin/gold-tasks', {
  default: () => [],
  retry: 0,
  timeout: 5_000,
})

const assignedTasks = computed(() => tasks.value.filter(task => task.status === 'ASSIGNED'))
const disagreements = computed(() => tasks.value.filter(task => task.status === 'DISAGREEMENT'))

function evidenceIds(value: string | undefined): string[] {
  return (value ?? '').split(',').map(item => item.trim()).filter(Boolean)
}

function arbitrationOptions(taskId: string): ArbitrationPacket['options'] {
  return arbitrationPackets.value[taskId]?.options ?? []
}

async function createTask(): Promise<void> {
  const annotators = [creation.annotatorA, creation.annotatorB]
    .map(value => value.trim())
    .filter(Boolean)
  try {
    await $fetch<GoldTask>('/api/v1/admin/gold-tasks', {
      method: 'POST',
      body: {
        sample_kind: creation.sampleKind,
        sample_ref: creation.sampleRef,
        source_code: creation.sourceCode,
        domain: creation.domain,
        production_decision_id: creation.productionDecisionId,
        assigned_annotator_ids: annotators,
        critical_safety: creation.criticalSafety,
        secondary_review_required: creation.criticalSafety || Boolean(creation.annotatorB),
        reason: creation.reason,
      },
      retry: 0,
      timeout: 5_000,
    })
    creation.sampleRef = ''
    await refresh()
    message.value = '金标任务已盲分配；标注人之间不会看到对方答案。'
  } catch {
    message.value = '任务未创建：请核对OIDC职责绑定、样本引用和双标要求。'
  }
}

async function loadArbitrationPacket(task: GoldTask): Promise<void> {
  try {
    arbitrationPackets.value[task.id] = await $fetch<ArbitrationPacket>(
      `/api/v1/admin/gold-tasks/${task.id}/arbitration-packet`,
      { retry: 0, timeout: 5_000 },
    )
  } catch {
    message.value = '仲裁材料不可用：当前身份可能参与过该任务标注。'
  }
}

async function submitAnnotation(task: GoldTask): Promise<void> {
  const decision = annotationDecision.value[task.id]?.trim()
  if (!decision) return
  busyTaskId.value = task.id
  try {
    await $fetch(`/api/v1/admin/gold-tasks/${task.id}/annotations`, {
      method: 'POST',
      body: {
        task_id: task.id,
        sample_kind: task.sample_kind,
        decision_code: decision.toUpperCase(),
        label_value: annotationLabel.value[task.id]?.trim() || null,
        evidence_ids: evidenceIds(annotationEvidence.value[task.id]),
        related_sample_refs: [],
      },
      retry: 0,
      timeout: 5_000,
    })
    await refresh()
    message.value = '标注已提交；响应未包含其他标注人的身份或答案。'
  } catch {
    message.value = '标注未保存：任务可能未分配给当前身份或已冻结。'
  } finally {
    busyTaskId.value = null
  }
}

async function arbitrate(task: GoldTask): Promise<void> {
  const selected = arbitrationSelection.value[task.id]?.trim()
  const reason = arbitrationReason.value[task.id]?.trim()
  if (!selected || !reason) return
  busyTaskId.value = task.id
  try {
    await $fetch(`/api/v1/admin/gold-tasks/${task.id}/arbitrations`, {
      method: 'POST',
      body: { task_id: task.id, selected_annotation_id: selected, reason },
      retry: 0,
      timeout: 5_000,
    })
    await refresh()
    message.value = '仲裁决定已不可变记录。'
  } catch {
    message.value = '仲裁失败：仅独立仲裁人可处理真实分歧。'
  } finally {
    busyTaskId.value = null
  }
}

async function freezeRelease(): Promise<void> {
  try {
    await $fetch('/api/v1/admin/gold-releases', {
      method: 'POST',
      body: {
        version: 'phase2-round17-gold-v1.0.0',
        reason: releaseReason.value,
      },
      retry: 0,
      timeout: 10_000,
    })
    await refresh()
    message.value = '第一阶段金标已按清单哈希冻结。'
  } catch {
    message.value = 'BLOCKED：样本量、关键安全双标或分歧仲裁尚未满足。'
  }
}
</script>

<template>
  <section class="gold-page">
    <PageHeader
      eyebrow="第一阶段人工评估"
      title="盲标与仲裁工作台"
      description="业务标注只引用Document、Event、Claim和Evidence标识；关键安全样本双人独立标注，分歧由独立仲裁人处理。"
    >
      <template #status>
        <StatusBadge tone="pending" label="HUMAN GOLD" />
        <span>{{ tasks.length }} 个可见任务</span>
      </template>
    </PageHeader>

    <p v-if="message" class="notice" aria-live="polite">{{ message }}</p>
    <p v-if="error" class="problem" role="alert">金标任务暂不可用；不会显示或缓存其他标注人的答案。</p>

    <section class="panel" aria-labelledby="assign-title">
      <div>
        <p class="eyebrow">仲裁人职责</p>
        <h2 id="assign-title">盲分配任务</h2>
      </div>
      <form class="form" @submit.prevent="createTask">
        <label>样本类型
          <select v-model="creation.sampleKind">
            <option value="DOCUMENT">Document</option>
            <option value="PAIR">重复候选对</option>
            <option value="EVENT">Event集合</option>
            <option value="CLAIM_EVIDENCE">Claim/Evidence</option>
            <option value="SEARCH_QUESTION">检索问题</option>
          </select>
        </label>
        <label>证据引用<input v-model.trim="creation.sampleRef" required maxlength="500"></label>
        <label>来源代码<input v-model.trim="creation.sourceCode" required pattern="[A-Z]{3}-[0-9]{3}" maxlength="7"></label>
        <label>领域
          <select v-model="creation.domain"><option value="DIGITAL">数字化</option><option value="SAFETY">安全</option></select>
        </label>
        <label>生产审批 UUIDv7<input v-model.trim="creation.productionDecisionId" required maxlength="36"></label>
        <label>标注人A UUIDv7<input v-model.trim="creation.annotatorA" required maxlength="36"></label>
        <label>标注人B UUIDv7<input v-model.trim="creation.annotatorB" :required="creation.criticalSafety" maxlength="36"></label>
        <label class="check"><input v-model="creation.criticalSafety" type="checkbox">关键安全样本（强制双标）</label>
        <label>分配依据<textarea v-model.trim="creation.reason" required maxlength="500" /></label>
        <button type="submit">创建盲标任务</button>
      </form>
    </section>

    <section class="panel" aria-labelledby="annotation-title">
      <div>
        <p class="eyebrow">标注人职责</p>
        <h2 id="annotation-title">我的独立标注</h2>
      </div>
      <p v-if="status === 'pending'" role="status">正在读取任务……</p>
      <ol v-else-if="assignedTasks.length" class="task-list">
        <li v-for="task in assignedTasks" :key="task.id">
          <div class="task-heading">
            <div><strong>{{ task.sample_kind }}</strong><p>{{ task.sample_ref }}</p></div>
            <StatusBadge :tone="task.critical_safety ? 'conflict' : 'pending'" :label="task.critical_safety ? '关键安全双标' : task.status" />
          </div>
          <form class="form" @submit.prevent="submitAnnotation(task)">
            <label>决定代码<input v-model.trim="annotationDecision[task.id]" required pattern="[A-Za-z][A-Za-z0-9_]+" maxlength="80"></label>
            <label>结构化标签<input v-model.trim="annotationLabel[task.id]" maxlength="2000"></label>
            <label>Evidence UUID（逗号分隔）<input v-model.trim="annotationEvidence[task.id]" maxlength="3700"></label>
            <button type="submit" :disabled="busyTaskId === task.id">提交独立标注</button>
          </form>
        </li>
      </ol>
      <EmptyState v-else title="暂无分配给当前身份的任务" icon="List" />
    </section>

    <section class="panel arbitration" aria-labelledby="arbitration-title">
      <div>
        <p class="eyebrow">与标注严格分离</p>
        <h2 id="arbitration-title">分歧仲裁</h2>
        <p>只有未参与该任务标注的仲裁人可提交决定；只显示稳定ID与稳定样本引用，不显示正文。</p>
      </div>
      <ol v-if="disagreements.length" class="task-list">
        <li v-for="task in disagreements" :key="task.id">
          <strong>{{ task.sample_kind }} · {{ task.sample_ref }}</strong>
          <button
            v-if="!arbitrationPackets[task.id]"
            type="button"
            @click="loadArbitrationPacket(task)"
          >
            读取盲化仲裁选项
          </button>
          <form class="form" @submit.prevent="arbitrate(task)">
            <fieldset v-if="arbitrationPackets[task.id]" class="options">
              <legend>选择有证据支持的标注</legend>
              <div
                v-for="option in arbitrationOptions(task.id)"
                :key="option.annotation_id"
                class="arbitration-option"
              >
                <label>
                  <input
                    v-model="arbitrationSelection[task.id]"
                    type="radio"
                    :value="option.annotation_id"
                    required
                  >
                  {{ option.decision_code }} · {{ option.label_value ?? '无附加标签' }}
                </label>
                <dl class="stable-references">
                  <div>
                    <dt>Evidence 稳定ID</dt>
                    <dd v-if="option.evidence_ids.length">
                      <code v-for="evidenceId in option.evidence_ids" :key="evidenceId">{{ evidenceId }}</code>
                    </dd>
                    <dd v-else>无</dd>
                  </div>
                  <div>
                    <dt>关联样本稳定引用</dt>
                    <dd v-if="option.related_sample_refs.length">
                      <code v-for="sampleRef in option.related_sample_refs" :key="sampleRef">{{ sampleRef }}</code>
                    </dd>
                    <dd v-else>无</dd>
                  </div>
                </dl>
              </div>
            </fieldset>
            <label>仲裁依据<textarea v-model.trim="arbitrationReason[task.id]" required maxlength="500" /></label>
            <button type="submit" :disabled="busyTaskId === task.id">记录仲裁</button>
          </form>
        </li>
      </ol>
      <EmptyState v-else title="暂无待仲裁分歧" icon="ShieldCheck" />
    </section>

    <section class="panel" aria-labelledby="freeze-title">
      <div><p class="eyebrow">不可变版本</p><h2 id="freeze-title">冻结 v1.0.0 金标</h2></div>
      <label>冻结依据<textarea v-model.trim="releaseReason" required maxlength="500" /></label>
      <button type="button" @click="freezeRelease">校验数量、双标和仲裁后冻结</button>
    </section>
  </section>
</template>

<style scoped>
.gold-page { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.panel { display: grid; gap: var(--spacing-4); padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.panel h2, .panel p { margin: 0; }
.eyebrow { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-weight-bold); letter-spacing: .08em; text-transform: uppercase; }
.form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-3); }
.form label, .panel > label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-weight: var(--font-weight-semibold); }
.form .check { display: flex; align-items: center; }
input, select, textarea, button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
button { width: fit-content; color: var(--color-surface); background: var(--color-brand-700); font-weight: var(--font-weight-semibold); }
.task-list { display: grid; margin: 0; padding: 0; list-style: none; gap: var(--spacing-3); }
.task-list li { display: grid; gap: var(--spacing-3); padding: var(--spacing-4); background: var(--color-surfaceMuted); border-radius: var(--radius-md); }
.task-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--spacing-3); }
.task-heading p { overflow-wrap: anywhere; color: var(--color-ink-500); }
.arbitration { border-color: var(--color-warning-300); }
.options { display: grid; gap: var(--spacing-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.arbitration-option { display: grid; gap: var(--spacing-2); padding: var(--spacing-3); background: var(--color-surface); border-radius: var(--radius-sm); }
.stable-references { display: grid; margin: 0; gap: var(--spacing-2); }
.stable-references div { display: grid; gap: var(--spacing-1); }
.stable-references dt { color: var(--color-ink-500); font-size: var(--text-xs); }
.stable-references dd { display: flex; flex-wrap: wrap; margin: 0; gap: var(--spacing-2); overflow-wrap: anywhere; }
.stable-references code { padding: var(--spacing-1) var(--spacing-2); background: var(--color-surfaceMuted); border-radius: var(--radius-xs); }
.notice, .problem { padding: var(--spacing-3); border-radius: var(--radius-sm); }
.notice { color: var(--color-brand-900); background: var(--color-brand-50); }
.problem { color: var(--color-danger-700); background: var(--color-danger-50); }
@media (max-width: 48rem) { .form { grid-template-columns: 1fr; } }
</style>
